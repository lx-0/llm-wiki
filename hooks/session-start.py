#!/usr/bin/env python3
"""
Session start hook — injects knowledge base context into Claude Code.

Reads knowledge/index.md and the most recent daily log, then outputs
structured JSON so the harness can prepend it to the session context.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

MAX_CONTEXT_CHARS = 20_000

WIKI_DIR = Path(__file__).resolve().parent.parent  # .wiki/
ROOT = WIKI_DIR.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
DAILY_DIR = ROOT / "daily"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"


def read_index() -> str:
    """Read the knowledge base index."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8").strip()
    return ""


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
    parts: list[str] = []

    # Today's date
    parts.append(f"Today's date: {datetime.now().strftime('%Y-%m-%d')}")

    # Knowledge base index
    index = read_index()
    if index:
        parts.append(f"# Knowledge Base Index\n\n{index}")

    # Recent daily log
    daily = read_recent_daily()
    if daily:
        parts.append(daily)

    context = "\n\n---\n\n".join(parts)

    # Truncate if needed
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n[... truncated ...]"

    return context


def main() -> None:
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
