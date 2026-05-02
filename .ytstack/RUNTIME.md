# Runtime

Services, APIs, env vars, and ports used by llm-wiki. The full pipeline description lives in `docs/PROCESS.md` (public engine doc); this file is the agent-facing operational summary.

## Services

- **LLM provider** — configurable per-install via `CONFIG.llm` (`config.yaml`). Default install supports Ollama (local) and OpenAI-compatible endpoints. Concrete provider, base URL, and model are set at `wiki setup` time.
- **Obsidian** — vault is rendered/edited via Obsidian. Engine writes Markdown; Obsidian reads. No live integration; filesystem-mediated.
- **Git** — engine repo + vault repo are both git-tracked but independent. Engine update via `wiki update`; vault is the user's own repo.

## Environment variables

(None required at engine level. All configuration is in `<vault>/.wiki/config.yaml`, generated from `config.example.yaml` by the setup wizard.)

LLM-provider-specific env vars (e.g. `OPENAI_API_KEY`) are read at runtime by the provider's SDK, but the engine itself does not read them directly.

## Ports

(None. Engine is CLI-only; no listening services in v0.x.)

## Deploy target

(None. Engine runs locally on the operator's machine alongside the vault. No remote deploy. Future: see `docs/plans/` for collectors that may run as cron / systemd services.)

## Pipeline overview

Full description: `docs/PROCESS.md`. Short version:

1. **Ingest** — collectors gather raw materials into `<vault>/raw/` (memories sync, email, web clippings, daily notes).
2. **Flush** — at session end / pre-compact, agent state is flushed to `raw/memories/`.
3. **Compile** — LLM-driven scripts (`scripts/compile_*.py`) read raw materials + existing `knowledge/` and produce / update Markdown articles in `knowledge/`.
4. **Render** — Obsidian renders the result. Optional: Dataview dashboards, Excalidraw diagrams.

## Hooks

- `hooks/session-end.py` — flushes Claude session state into `raw/memories/`.
- `hooks/pre-compact.py` — same flush triggered before context compaction.
- Both spawn `flush.py` via `uv run --project <vault>/.wiki`.
