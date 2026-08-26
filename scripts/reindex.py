"""`wiki reindex` — deterministic knowledge/index.md reconciliation (M031-S02).

Thin CLI over core.index_sync (the same pass compile runs automatically):
dedupe duplicate rows (last wins), drop dangling rows, append missing
articles with first-paragraph summaries. `--dry-run` prints the stats
without writing.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import TIMEZONE  # noqa: E402  (a tz NAME string, not tzinfo)
from core.index_sync import sync_index  # noqa: E402
from core.paths import KNOWLEDGE_DIR, ROOT_DIR  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wiki reindex",
        description="Reconcile knowledge/index.md against the corpus (deterministic).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args(argv)

    stats = sync_index(
        KNOWLEDGE_DIR, ROOT_DIR,
        today=datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d"),
        apply=not args.dry_run,
    )
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"index sync ({mode}): {stats['rows_before']} rows before · "
        f"{stats['kept']} kept · {stats['deduped']} deduped · "
        f"{stats['dropped_dangling']} dropped · {stats['appended']} appended · "
        f"changed={stats['changed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
