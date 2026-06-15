"""Eager path constants for the engine — computed from `__file__`, zero deps.

This module is the dependency-free base of the config layer: every path the
engine touches is derived here, once, from this file's location. Importing it
has no side effects and pulls in nothing but `pathlib`.

Split rationale (architecture-deepening #2, 2026-05-14): path-construction was
scattered across ~20 sites and tangled with the YAML-driven `CONFIG` singleton
inside one `config.py`. The two have different natures — pure `__file__`-derived
constants vs. lazy stateful config — and now live in honestly-named modules:
`paths.py` (here) and `config.py` (the `CONFIG` singleton). `core/utils.py` owns
the datetime helpers (`now_iso` / `today_iso`).
"""

from pathlib import Path

# ── Layout ─────────────────────────────────────────────────────────────
#   <vault>/                ← ROOT_DIR (user-visible content)
#   ├── .wiki/              ← WIKI_DIR (engine, hidden from Obsidian)
#   │   ├── scripts/        ← SCRIPTS_DIR
#   │   │   └── core/       ← CORE_DIR (this file lives here)
#   │   ├── hooks/          ← HOOKS_DIR
#   │   ├── prompts/        ← (render() templates, loaded by core/prompts.py)
#   │   │   └── agents/     ← AGENT_SPECS_DIR (agent-task specs, core/agent_spec.py)
#   │   ├── config.yaml     ← (loaded by core/config.py)
#   │   ├── .claude/.env    ← DOTENV_FILE (loaded by core/config.py at import)
#   │   ├── state/          ← STATE_DIR (json hash trackers / cooldowns / dedup)
#   │   ├── logs/           ← LOGS_DIR (flush + compile log output; LOG_FILE = operations.md)
#   │   ├── sessions/       ← SESSIONS_DIR (session-flush staging + failed-flushes/)
#   │   └── reports/        ← REPORTS_DIR (lint + review-wiki output)
#   ├── daily/, raw/, knowledge/, inbox/   ← user-visible content
#   └── AGENTS.md, README.md, ...
CORE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CORE_DIR.parent
WIKI_DIR = SCRIPTS_DIR.parent
ROOT_DIR = WIKI_DIR.parent

# ── Vault content (user-visible) ───────────────────────────────────────
DAILY_DIR = ROOT_DIR / "daily"
RAW_DIR = ROOT_DIR / "raw"
RAW_INBOX_WIKI_DIR = RAW_DIR / "inbox-wiki"
RAW_ARTICLES_DIR = RAW_DIR / "articles"
RAW_PAPERS_DIR = RAW_DIR / "papers"
RAW_NOTES_DIR = RAW_DIR / "notes"
RAW_TRANSCRIPTS_DIR = RAW_DIR / "transcripts"
RAW_AUDIO_DIR = RAW_DIR / "audio"
RAW_REQUESTS_DIR = RAW_DIR / "requests"
RAW_SUGGESTIONS_DIR = RAW_DIR / "suggestions"
INBOX_DIR = ROOT_DIR / "inbox"
WORKSPACE_DIR = ROOT_DIR / "workspace"        # operator working layer (intent-dispatch + todo)
WORKSPACE_INBOX_DIR = WORKSPACE_DIR / "inbox"  # detected intents awaiting triage (task/idea/note)
WORKSPACE_TASKS_DIR = WORKSPACE_DIR / "tasks"  # accepted tasks, numbered (001.md, 002.md, …); listed in todo.md
WORKSPACE_TODO = WORKSPACE_DIR / "todo.md"     # the todo list — accepted tasks appended as checkbox lines
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
QA_DIR = KNOWLEDGE_DIR / "qa"
PEOPLE_DIR = KNOWLEDGE_DIR / "people"
PROJECTS_DIR = KNOWLEDGE_DIR / "projects"
AREAS_DIR = KNOWLEDGE_DIR / "areas"
FACTS_DIR = KNOWLEDGE_DIR / "facts"
TAKES_DIR = KNOWLEDGE_DIR / "takes"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"

# ── Engine internals (under .wiki/) ────────────────────────────────────
HOOKS_DIR = WIKI_DIR / "hooks"
AGENT_SPECS_DIR = WIKI_DIR / "prompts" / "agents"  # agent-task specs (*.md) — see core/agent_spec.py
REPORTS_DIR = WIKI_DIR / "reports"  # lint + review-wiki output; under .wiki/, not vault root
CONFIG_FILE = WIKI_DIR / "config.yaml"
DOTENV_FILE = ROOT_DIR / ".claude" / ".env"

# ── Per-instance runtime artifacts (gitignored, flat under .wiki/) ─────
STATE_DIR = WIKI_DIR / "state"        # *.json — hash trackers, dedup windows, cooldowns
LOGS_DIR = WIKI_DIR / "logs"          # *.log  — flush + compile output
SESSIONS_DIR = WIKI_DIR / "sessions"  # session-flush staging + failed-flushes/
STATE_FILE = STATE_DIR / "state.json"
EMAIL_STATE_FILE = STATE_DIR / "email-state.json"
# Operations audit log (engine + agent-side append). Lives under .wiki/logs/
# (not knowledge/) so it's invisible to Obsidian indexing — a 2 MB log.md
# inside knowledge/ crashed the vault on 2026-05-28 (lxw). Agents reach it
# via the path-scope hook in compile_stages/compile.py + dream.py.
LOG_FILE = LOGS_DIR / "operations.md"
