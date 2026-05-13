"""
Retry previously-failed flush extractions from scripts/failed-flushes/.

When flush.py cannot extract (rate limit, API error), the context file is
archived instead of deleted. This script retries them one by one — on success,
the context is appended to the daily log and removed from the archive; on
repeated failure, it stays archived for the next run.

Runs as a daily piggyback task.

Usage:
    uv run python scripts/retry-failed-flushes.py
    uv run python scripts/retry-failed-flushes.py --dry-run
    uv run python scripts/retry-failed-flushes.py --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Must be set BEFORE importing claude_agent_sdk
import os
os.environ["CLAUDE_INVOKED_BY"] = "flush_retry"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import flush_pipeline
from flush import extract_from_context
from core.wiki_config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
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

    log.info("Retrying %s (%d chars)", staged.path.name, len(context))
    extracted = await extract_from_context(context)

    if not extracted:
        log.warning("Retry failed — keeping %s in archive", staged.path.name)
        return False

    daily_file = flush_pipeline.append_to_daily(extracted, staged.session_id)
    log.info("Appended retry result to %s", daily_file.name)
    flush_pipeline.mark_complete(staged)
    return True


async def main_async(dry_run: bool, limit: int) -> None:
    archived = list(flush_pipeline.pending(limit=limit))
    if not archived:
        log.info("No archived flushes to retry")
        return

    log.info("Found %d archived flush(es)", len(archived))

    succeeded = 0
    for staged in archived:
        if await retry_one(staged, dry_run):
            succeeded += 1

    log.info("Retry complete: %d/%d succeeded", succeeded, len(archived))


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry failed flushes")
    parser.add_argument("--dry-run", action="store_true")
    _retry_pb = CONFIG.piggybacks.get("retry_failed_flushes")
    _default_limit = (_retry_pb.max_per_run if _retry_pb else None) or 5
    parser.add_argument("--limit", type=int, default=_default_limit, help="Max retries per run")
    args = parser.parse_args()
    asyncio.run(main_async(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
