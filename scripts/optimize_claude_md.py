"""Optimize ~/.claude/CLAUDE.md based on wiki knowledge.

Reads the compiled wiki, identifies cross-project patterns, and updates
the global CLAUDE.md. Runs daily as a piggyback task in flush.py.

Usage:
    uv run python scripts/optimize_claude_md.py              # optimize
    uv run python scripts/optimize_claude_md.py --dry-run    # show diff without writing
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "optimize_claude_md"

import argparse
import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import query

from core.console import setup_console_logging
from core.paths import LOG_FILE, ROOT_DIR, STATE_DIR
from core.prompts import render
from core.sdk_helpers import SdkCallSpec, WriteScope, run_sdk_query
from core.utils import now_iso, read_wiki_index_compact

# ── Config ──────────────────────────────────────────────────────────

CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
BACKUP_DIR = ROOT_DIR / "raw" / "notes" / "claude-md-backups"
# The agent edits this copy, never CLAUDE.md itself; the engine copies it over after
# the size check. It used to sit at `<vault>/scripts/`, a pre-split path no vault has
# any more (FileNotFoundError on every opted-in run).
STAGING_FILE = STATE_DIR / "claude-md-staged.md"

log = logging.getLogger("optimize-claude-md")

# ── Main ────────────────────────────────────────────────────────────


async def optimize(dry_run: bool = False) -> None:
    if not CLAUDE_MD.exists():
        log.error("CLAUDE.md not found: %s", CLAUDE_MD)
        return

    current = CLAUDE_MD.read_text(encoding="utf-8")
    current_lines = len(current.strip().split("\n"))
    index_md = read_wiki_index_compact()

    log.info("Current CLAUDE.md: %d lines, %d chars", current_lines, len(current))
    log.info("Wiki: %d chars compact index", len(index_md))

    if dry_run:
        log.info(
            "[dry-run] Would optimize CLAUDE.md based on %d chars of wiki index", len(index_md)
        )
        return

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"CLAUDE.md.backup-{ts}"
    shutil.copy2(CLAUDE_MD, backup)
    log.info("Backup: %s", backup)

    # The agent edits a staged copy in the engine's state dir; we copy it back.
    staging = STAGING_FILE
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CLAUDE_MD, staging)

    prompt = render(
        "optimize_claude_md",
        current_claude_md=current,
        index_md=index_md,
        claude_md_path=str(staging),
        current_lines=current_lines,
    )

    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label="optimize_claude_md",
            logger=log,
            cwd=ROOT_DIR,
            max_turns=10,
            system_prompt={"type": "preset", "preset": "claude_code"},
            allowed_tools=("Read", "Edit", "Grep"),
            # The prompt embeds the wiki index, which compile distils from substrate:
            # the agent may edit the staged copy and nothing else.
            write_scope=WriteScope(roots=(staging,)),
            source=str(staging),
            input_chars=len(prompt),
        ),
        query_fn=query,
    )
    if not result.ok:
        staging.unlink(missing_ok=True)
        return
    log.info("Result: %s", result.result_text[:300])

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

        diff = list(
            difflib.unified_diff(
                current.splitlines(),
                updated.splitlines(),
                fromfile="CLAUDE.md (before)",
                tofile="CLAUDE.md (after)",
                lineterm="",
            )
        )
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
    log.info("Done. Diff logged to %s", LOG_FILE)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize ~/.claude/CLAUDE.md from wiki knowledge")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without writing"
    )
    args = parser.parse_args()
    await optimize(dry_run=args.dry_run)


if __name__ == "__main__":
    setup_console_logging("optimize-claude-md")
    asyncio.run(main())
