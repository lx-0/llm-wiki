"""Optimize ~/.claude/CLAUDE.md based on wiki knowledge.

Reads the compiled wiki, identifies cross-project patterns, and updates
the global CLAUDE.md. Runs daily as a piggyback task in flush.py.

Usage:
    uv run python scripts/optimize-claude-md.py              # optimize
    uv run python scripts/optimize-claude-md.py --dry-run    # show diff without writing
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "optimize_claude_md"

import argparse
import asyncio
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from core.config import KNOWLEDGE_DIR, ROOT_DIR, now_iso
from core.utils import read_all_wiki_content, read_wiki_index

# ── Config ──────────────────────────────────────────────────────────

CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
BACKUP_DIR = ROOT_DIR / "raw" / "notes" / "claude-md-backups"
LOG_FILE = KNOWLEDGE_DIR / "log.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("optimize-claude-md")

from core.prompts import render  # noqa: E402
from core.sdk_helpers import StderrCapture, log_sdk_failure  # noqa: E402
import time as _time  # noqa: E402

# ── Main ────────────────────────────────────────────────────────────

async def optimize(dry_run: bool = False) -> None:
    if not CLAUDE_MD.exists():
        log.error("CLAUDE.md not found: %s", CLAUDE_MD)
        return

    current = CLAUDE_MD.read_text(encoding="utf-8")
    current_lines = len(current.strip().split("\n"))
    index_md = read_wiki_index()
    wiki_content = read_all_wiki_content()

    log.info("Current CLAUDE.md: %d lines, %d chars", current_lines, len(current))
    log.info("Wiki: %d chars index, %d chars content", len(index_md), len(wiki_content))

    if dry_run:
        log.info("[dry-run] Would optimize CLAUDE.md based on %d chars of wiki content", len(wiki_content))
        return

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"CLAUDE.md.backup-{ts}"
    shutil.copy2(CLAUDE_MD, backup)
    log.info("Backup: %s", backup)

    # Agent writes to a staging file in the vault, then we copy it
    staging = ROOT_DIR / "scripts" / "claude-md-staged.md"
    shutil.copy2(CLAUDE_MD, staging)

    prompt = render(
        "optimize_claude_md",
        current_claude_md=current,
        index_md=index_md,
        wiki_content=wiki_content,
        claude_md_path=str(staging),
        current_lines=current_lines,
    )

    started = _time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                allowed_tools=["Read", "Edit", "Grep"],
                permission_mode="acceptEdits",
                max_turns=10,
                system_prompt={"type": "preset", "preset": "claude_code"},
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, ResultMessage):
                log.info("Result: %s", message.result[:300])
    except Exception as exc:
        log_sdk_failure(
            log,
            label="optimize_claude_md",
            source=str(staging),
            model="(default)",
            input_chars=len(prompt),
            started=started,
            capture=capture,
            exc=exc,
        )
        staging.unlink(missing_ok=True)
        return

    if not staging.exists():
        log.error("Staging file missing! Skipping.")
        return

    updated = staging.read_text(encoding="utf-8")
    staging.unlink(missing_ok=True)
    updated_lines = len(updated.strip().split("\n"))

    if updated == current:
        log.info("No changes made.")
        backup.unlink()  # no need for backup if nothing changed
        return

    log.info("Updated: %d → %d lines", current_lines, updated_lines)

    if updated_lines > 200:
        log.warning("CLAUDE.md exceeds 200 lines (%d)! Restoring backup.", updated_lines)
        shutil.copy2(backup, CLAUDE_MD)
        return

    # Log the diff
    if LOG_FILE.exists():
        import difflib
        diff = list(difflib.unified_diff(
            current.splitlines(), updated.splitlines(),
            fromfile="CLAUDE.md (before)", tofile="CLAUDE.md (after)", lineterm=""
        ))
        if diff:
            diff_text = "\n".join(diff[:50])  # limit diff size
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n\n## [{now_iso()}] optimize-claude-md\n")
                f.write(f"- Lines: {current_lines} → {updated_lines}\n")
                f.write(f"- Backup: {backup.name}\n")
                f.write(f"```diff\n{diff_text}\n```\n")

    # Apply: copy staged version to CLAUDE.md
    CLAUDE_MD.write_text(updated, encoding="utf-8")
    log.info("Applied to %s", CLAUDE_MD)
    log.info("Done. Diff logged to knowledge/log.md")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize ~/.claude/CLAUDE.md from wiki knowledge")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    args = parser.parse_args()
    await optimize(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
