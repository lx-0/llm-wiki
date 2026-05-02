"""Path constants and configuration for the personal knowledge base."""

from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────
# Layout:
#   <vault>/                ← ROOT_DIR (user-visible content + tooling root)
#   ├── .wiki/              ← WIKI_DIR (operational, hidden from Obsidian)
#   │   ├── scripts/        ← SCRIPTS_DIR  (this file lives here)
#   │   ├── hooks/          ← HOOKS_DIR
#   │   ├── prompts/        ← (loaded by prompts.py)
#   │   └── config.yaml     ← (loaded by wiki_config.py)
#   ├── daily/, raw/, knowledge/, inbox/   ← user-visible content
#   ├── reports/            ← REPORTS_DIR — lint + review-wiki output, user-visible
#   └── AGENTS.md, README.md, ...
SCRIPTS_DIR = Path(__file__).resolve().parent
WIKI_DIR = SCRIPTS_DIR.parent
ROOT_DIR = WIKI_DIR.parent
DAILY_DIR = ROOT_DIR / "daily"
RAW_DIR = ROOT_DIR / "raw"
RAW_ARTICLES_DIR = RAW_DIR / "articles"
RAW_PAPERS_DIR = RAW_DIR / "papers"
RAW_NOTES_DIR = RAW_DIR / "notes"
RAW_TRANSCRIPTS_DIR = RAW_DIR / "transcripts"
RAW_AUDIO_DIR = RAW_DIR / "audio"
INBOX_DIR = ROOT_DIR / "inbox"
RAW_REQUESTS_DIR = RAW_DIR / "requests"
RAW_SUGGESTIONS_DIR = RAW_DIR / "suggestions"
RAW_MEMORIES_DIR = RAW_DIR / "memories"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
CONNECTIONS_DIR = KNOWLEDGE_DIR / "connections"
QA_DIR = KNOWLEDGE_DIR / "qa"
PEOPLE_DIR = KNOWLEDGE_DIR / "people"
PROJECTS_DIR = KNOWLEDGE_DIR / "projects"
REPORTS_DIR = ROOT_DIR / "reports"  # vault-root, user-visible (lint + review-wiki output)
HOOKS_DIR = WIKI_DIR / "hooks"
AGENTS_FILE = ROOT_DIR / "AGENTS.md"

INDEX_FILE = KNOWLEDGE_DIR / "index.md"
LOG_FILE = KNOWLEDGE_DIR / "log.md"

# Per-instance runtime artifacts — gitignored, live alongside the .wiki/ checkout.
# Split into two folders so JSON state and log files don't intermingle.
STATE_DIR = SCRIPTS_DIR / "state"      # *.json — hash trackers, dedup windows, cooldowns
LOGS_DIR = SCRIPTS_DIR / "logs"        # *.log  — flush + compile output

STATE_FILE = STATE_DIR / "state.json"
EMAIL_STATE_FILE = STATE_DIR / "email-state.json"

# ── Timezone ───────────────────────────────────────────────────────────
# Sourced from CONFIG.scheduling.timezone (default "UTC"); override via config.yaml.
from wiki_config import CONFIG  # noqa: E402  (import here to avoid early-init circularity)
TIMEZONE = CONFIG.scheduling.timezone


def now_iso() -> str:
    """Current time in ISO 8601 format."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date in ISO 8601 format."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
