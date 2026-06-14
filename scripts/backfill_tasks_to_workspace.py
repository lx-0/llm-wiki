"""One-shot: migrate the legacy `tasks/` intent-queue to `workspace/inbox/`.

The intent-dispatch queue moved from a top-level `tasks/` folder to the
`workspace/` working layer (`workspace/inbox/`) when the producer was broadened
to task/idea/note (2026-06-14). This moves any existing `tasks/*.md` records
into `workspace/inbox/` and removes the empty `tasks/` dir. Idempotent: a vault
already on the new layout (no `tasks/`) produces no change. Records already
present in `workspace/inbox/` are left untouched (never overwritten).

Usage:
    wiki backfill tasks-to-workspace            # apply
    wiki backfill tasks-to-workspace --dry-run  # show what would move
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paths import ROOT_DIR, WORKSPACE_INBOX_DIR  # noqa: E402

log = logging.getLogger("backfill-tasks-to-workspace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dry-run", action="store_true", help="show what would move")
    args = ap.parse_args()

    old = ROOT_DIR / "tasks"
    if not old.is_dir():
        log.info("no legacy tasks/ dir — already on workspace/inbox/ layout.")
        return 0
    records = sorted(old.glob("*.md"))
    if not records:
        if not args.dry_run:
            try:
                old.rmdir()
                log.info("removed empty tasks/.")
            except OSError:
                pass
        else:
            log.info("[dry-run] tasks/ is empty — would remove it.")
        return 0

    moved = skipped = 0
    for r in records:
        dest = WORKSPACE_INBOX_DIR / r.name
        if dest.exists():
            log.info("skip (exists): workspace/inbox/%s", r.name)
            skipped += 1
            continue
        log.info("move: tasks/%s → workspace/inbox/%s", r.name, r.name)
        if not args.dry_run:
            WORKSPACE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(r), str(dest))
            moved += 1

    if args.dry_run:
        log.info("[dry-run] %d would move, %d already present. Re-run without --dry-run.", len(records), skipped)
        return 0
    # remove tasks/ if now empty
    if not any(old.iterdir()):
        try:
            old.rmdir()
        except OSError:
            pass
    log.info("moved %d record(s) to workspace/inbox/ (%d skipped).", moved, skipped)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
