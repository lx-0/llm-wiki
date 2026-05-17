"""Migrate mobile-collector `.processed/` archives into the vault audit zone.

Pre-M022, the voice and pictures collectors archived processed source files
in-place under `<voice_inbox>/.processed/` and `<picture_inbox>/.processed/`
— i.e. inside the operator's iCloud Drive drop zone, outside the vault. M022
relocates those archives to `<vault>/raw/inbox-mobile/voice/` and
`<vault>/raw/inbox-mobile/pictures/` (two-zone intake: audit-archive lives in
the vault next to substrate).

This one-shot migration moves any pre-existing `.processed/*` files into
their new vault home. Idempotent — re-running after a successful migration
finds nothing to do. Graceful — skips silently when `voice_inbox` /
`picture_inbox` are unconfigured. After moving, the now-empty `.processed/`
subdir is rmdir-ed.

Usage:
    uv run --project .wiki python scripts/migrations/migrate_inbox_archive.py
    uv run --project .wiki python scripts/migrations/migrate_inbox_archive.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import CONFIG
from core.paths import RAW_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-inbox-archive")


SOURCES = (
    ("voice", "voice_inbox"),
    ("pictures", "picture_inbox"),
)


def _migrate_one(source_name: str, inbox_attr: str, dry_run: bool) -> dict:
    """Move <inbox>/.processed/* into <vault>/raw/inbox-mobile/<source_name>/.

    Returns a stats dict with moved/collisions/skipped/rmdir keys.
    """
    stats = {"moved": 0, "collisions": 0, "skipped_reason": None, "rmdir": False}
    inbox_str = (getattr(CONFIG.personal, inbox_attr, "") or "").strip()
    if not inbox_str:
        stats["skipped_reason"] = f"CONFIG.personal.{inbox_attr} unset"
        log.info("%s: skipped (%s)", source_name, stats["skipped_reason"])
        return stats

    inbox = Path(inbox_str).expanduser()
    legacy = inbox / ".processed"
    if not legacy.exists():
        stats["skipped_reason"] = f"{legacy} does not exist"
        log.info("%s: nothing to migrate (%s)", source_name, stats["skipped_reason"])
        return stats

    dest = RAW_DIR / "inbox-mobile" / source_name
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    for src in sorted(legacy.iterdir()):
        if src.is_dir():
            continue
        dst = dest / src.name
        if dst.exists():
            mtime = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y%m%dT%H%M%S")
            dst = dest / f"{src.stem}-{mtime}{src.suffix}"
            stats["collisions"] += 1
        if dry_run:
            log.info("%s: would move %s → %s", source_name, src, dst)
        else:
            shutil.move(str(src), str(dst))
            log.info("%s: moved %s → %s", source_name, src.name, dst.relative_to(RAW_DIR.parent))
        stats["moved"] += 1

    if dry_run:
        log.info("%s: dry-run — would move %d files (%d collisions)", source_name, stats["moved"], stats["collisions"])
        return stats

    log.info("%s: moved %d files → %s (%d collisions resolved)", source_name, stats["moved"], dest, stats["collisions"])
    try:
        legacy.rmdir()
        stats["rmdir"] = True
        log.info("%s: removed empty %s", source_name, legacy)
    except OSError as exc:
        log.warning("%s: rmdir %s failed (non-empty or permission?): %s", source_name, legacy, exc)

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate <inbox>/.processed/ into vault audit zone")
    parser.add_argument("--dry-run", action="store_true", help="Show what would move without writing")
    args = parser.parse_args(argv)

    if args.dry_run:
        log.info("=== DRY RUN — no files will be moved ===")

    total_moved = 0
    for source_name, inbox_attr in SOURCES:
        stats = _migrate_one(source_name, inbox_attr, dry_run=args.dry_run)
        total_moved += stats["moved"]

    log.info("Migration complete: %d files %s", total_moved, "would move" if args.dry_run else "moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
