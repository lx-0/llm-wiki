# Backlog: `wiki doctor` should smoke-import the declared dependencies

Found 2026-08-26 while verifying kcma-d8 after an operator restart.

## What happened

`review-wiki` failed in 0.1 s with exit 1. Not Ollama — the vault venv had
**partially materialized packages**: whole subpackages missing from otherwise
intact installs.

```
httpx/                     → _transports/ directory absent
claude_agent_sdk           → ModuleNotFoundError: No module named 'mcp.client'
prompt_toolkit             → No module named 'prompt_toolkit.application.current'
```

`import httpx` therefore raised at module load, which takes down every
HTTP-using surface (ollama_client → curiosity producer + review-wiki, oura,
jamie, gmeet, calendar, publish) and — via `claude_agent_sdk` — compile,
flush, dream and publish as well. The engine looks installed: `.dist-info`
present, version correct, most modules importable. Only the import fails.

`uv sync --reinstall` in `<vault>/.wiki` repaired all three; every declared
dependency imports cleanly afterwards.

## Cause: not established

Two plausible mechanisms, neither confirmed:

1. **iCloud eviction.** The vault (and therefore `.venv`) lives under
   `~/Library/Mobile Documents/`. iCloud can evict file contents it considers
   cold; a `.venv` is thousands of rarely-opened files. This would explain
   whole directories vanishing while metadata stays.
2. **An interrupted `uv` operation.** A `uv run` was killed by a foreground
   timeout during this session at roughly the time the first failure appeared.

Evidence against a simple "always broken": a probe at 15:36 imported `httpx`
and ran three live Ollama calls successfully; the first import failure was at
15:53. So it broke *during* the session.

## Why it deserves a check

This is the highest-blast-radius silent failure the vault can have — it kills
compile, flush, publish and every collector at once — and nothing surfaces it
until a piggyback dies with an exit code and no stderr (the runner routes child
output to DEVNULL). It is exactly the M031 class: a failure you cannot see.

## Proposed shape

A `dependencies-importable` check in `core/health.py`, non-quick only:

- read the declared dependency list (parse `pyproject.toml`'s
  `[project].dependencies`, so it can never drift from what is actually
  declared — same derive-don't-duplicate rule the config registries follow),
- map distribution name → import name where they differ (`pyyaml`→`yaml`,
  `python-dotenv`→`dotenv`, `pillow`→`PIL`, `claude-agent-sdk`→
  `claude_agent_sdk`, `youtube-transcript-api`→`youtube_transcript_api`,
  `yt-dlp`→`yt_dlp`, `google-auth`→`google.auth`),
- `importlib.import_module` each in a subprocess (so a broken C extension
  can't take the doctor down with it), report every failure as **critical**
  with `fix: "cd <vault>/.wiki && uv sync --reinstall"` and
  `dispatch_args` left None (it is a shell fix, not a `wiki` subcommand).

Cost is a few hundred ms and no network. Guard against the mapping table
drifting: a test that asserts every declared distribution resolves to an
importable module in the dev checkout.

## Note when picking this up

Do NOT hand-maintain a second list of dependency names — that is the exact
"fourth hand registry" mistake the config loader made (KNOWLEDGE.md,
2026-08-25). Derive from `pyproject.toml`, and keep only the
distribution→import-name exceptions as data.
