"""
Retry previously-failed flush extractions from `.wiki/sessions/failed-flushes/`.

When flush.py cannot extract (rate limit, API error, a reply in the wrong shape),
the context file is archived instead of deleted. This script retries them one by
one, oldest first — on success, the context goes into the daily log of the day it
was staged (not the retry day) and leaves the archive; a conversation with nothing
worth keeping (`NOTHING_TO_SAVE`) leaves it without a block; on repeated failure,
it stays archived for the next run. A day that already holds a newer block of the
same session keeps it: the retry is then redundant and spends no extraction.

Runs as a daily piggyback task, `--limit` contexts per run; the log names the
queue's depth.

Usage:
    uv run python scripts/retry_failed_flushes.py
    uv run python scripts/retry_failed_flushes.py --dry-run
    uv run python scripts/retry_failed_flushes.py --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import logging

# Must be set BEFORE importing claude_agent_sdk
import os

os.environ["CLAUDE_INVOKED_BY"] = "flush_retry"

from core import flush_pipeline
from core.config import CONFIG
from core.console import setup_console_logging
from flush import ERRORS_LOG_FILE, LOG_FILE, NOTHING_TO_SAVE, extract_from_context

log = logging.getLogger("retry-failed-flushes")


async def retry_one(staged: flush_pipeline.StagedFlush, dry_run: bool) -> bool:
    """Returns True if retry succeeded (file removed from archive)."""
    context = staged.path.read_text(encoding="utf-8")
    if not context.strip():
        log.warning("Empty context — discarding %s", staged.path.name)
        if not dry_run:
            flush_pipeline.mark_complete(staged)
        return True

    if dry_run:
        log.info("[dry-run] would retry %s (%d chars)", staged.path.name, len(context))
        return False

    when = flush_pipeline.staged_at(staged)
    if when is not None:
        existing = flush_pipeline.session_block_time(staged.session_id, when)
        if existing is not None and existing >= when.strftime("%H:%M:%S"):
            log.info(
                "Session %s already has a newer block in daily/%s (%s) — dropping %s",
                staged.session_id,
                when.strftime("%Y-%m-%d"),
                existing,
                staged.path.name,
            )
            flush_pipeline.mark_complete(staged)
            return True

    log.info("Retrying %s (%d chars)", staged.path.name, len(context))
    extracted = await extract_from_context(context)

    if extracted == NOTHING_TO_SAVE:
        log.info("Nothing worth keeping in %s — dropping it", staged.path.name)
        flush_pipeline.mark_complete(staged)
        return True

    if not extracted:
        log.warning("Retry failed — keeping %s in archive", staged.path.name)
        return False

    daily_file = flush_pipeline.append_to_daily(extracted, staged.session_id, when=when)
    log.info("Appended retry result to %s/%s", daily_file.parent.name, daily_file.name)
    flush_pipeline.mark_complete(staged)
    return True


async def main_async(dry_run: bool, limit: int) -> None:
    queue = list(flush_pipeline.pending())
    if not queue:
        log.info("No archived flushes to retry")
        return

    archived = queue[:limit]
    log.info("Found %d archived flush(es) — retrying %d this run", len(queue), len(archived))

    succeeded = 0
    for staged in archived:
        if await retry_one(staged, dry_run):
            succeeded += 1

    log.info("Retry complete: %d/%d succeeded", succeeded, len(archived))


def main() -> None:
    # Runs as a piggyback with stdio on DEVNULL (core.piggybacks): the archive in
    # flush.log / flush-errors.log is its only trace — the same files this process
    # wrote to while it still inherited flush's import-time setup.
    setup_console_logging("retry-failed-flushes", log_file=LOG_FILE, error_file=ERRORS_LOG_FILE)
    parser = argparse.ArgumentParser(description="Retry failed flushes")
    parser.add_argument("--dry-run", action="store_true")
    _retry_pb = CONFIG.piggybacks.get("retry_failed_flushes")
    _default_limit = (_retry_pb.max_per_run if _retry_pb else None) or 5
    parser.add_argument("--limit", type=int, default=_default_limit, help="Max retries per run")
    args = parser.parse_args()
    asyncio.run(main_async(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
