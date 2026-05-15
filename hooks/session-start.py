#!/usr/bin/env python3
"""
Session start hook — injects a wiki pointer block + recent daily tail.

Hands the agent a map of where to look (paths + how to use them) instead of
embedding the catalog. The agent pulls articles on demand via Read/Grep —
matches Karpathy's pull-based pattern and avoids the 20k-char cap that
previously meant ~7% of a 297 KB index reached the model anyway.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent  # .wiki/
ROOT = WIKI_DIR.parent
DAILY_DIR = ROOT / "daily"

POINTER_BLOCK = """# Knowledge base
- Index: `knowledge/index.md` — flat catalog of all wiki articles. One row per article (link, summary, sources, date). Grep by topic, then Read the matched article(s). Don't try to load the full index — it's large.
- Articles by type: `knowledge/concepts/`, `knowledge/projects/`, `knowledge/people/`, `knowledge/facts/`, `knowledge/MOCs/`, `knowledge/connections/`, `knowledge/qa/`.
- Raw substrate (read-only, never write): `raw/notes/`, `raw/articles/`, `raw/transcripts/`, `raw/papers/`, `daily/`.
- Schema + conventions: `AGENTS.md` at vault root."""


def read_recent_daily(max_lines: int = 30) -> str:
    """Read the most recent daily log (today or yesterday, last N lines)."""
    today = datetime.now()
    for delta in range(2):  # today, then yesterday
        day = today - timedelta(days=delta)
        daily_file = DAILY_DIR / f"{day.strftime('%Y-%m-%d')}.md"
        if daily_file.exists():
            lines = daily_file.read_text(encoding="utf-8").splitlines()
            snippet = "\n".join(lines[-max_lines:])
            return f"# Recent Daily Log ({day.strftime('%Y-%m-%d')})\n\n{snippet}"
    return ""


def build_context() -> str:
    """Build the full context string."""
    parts: list[str] = [
        f"Today's date: {datetime.now().strftime('%Y-%m-%d')}",
        POINTER_BLOCK,
    ]

    daily = read_recent_daily()
    if daily:
        parts.append(daily)

    return "\n\n---\n\n".join(parts)


def main() -> None:
    # Recursion guard: when compile.py / query.py / agent_task.py / etc. spawn
    # the bundled Claude CLI as a subprocess, this hook fires inside that
    # subprocess and re-injects the daily-log + wiki-pointer context on top of
    # the carefully-budgeted compile prompt. On 2026-05-15 that contributed to
    # a context-overflow + rate-limit cascade that aborted a full compile run.
    # Sibling hooks (session-end, pre-compact) already have this guard; adding
    # it here closes the gap. The CLI invoker sets CLAUDE_INVOKED_BY in
    # scripts/{compile,query,agent_task,flush}.py.
    if os.environ.get("CLAUDE_INVOKED_BY"):
        # Emit an empty hookSpecificOutput so the SDK doesn't think the hook
        # crashed; just contribute no extra context to engine-launched sessions.
        json.dump({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""}}, sys.stdout)
        return
    context = build_context()
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
