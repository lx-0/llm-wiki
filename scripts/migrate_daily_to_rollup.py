"""One-shot migration: daily/<date>.md → daily/<date>/sessions.md.

Idempotent — re-running is safe. Run once per vault by the operator:

    uv run python scripts/migrate_daily_to_rollup.py --vault <path> [--dry-run]

This script COPIES (does not move) existing flat daily files into the
new per-source subfolder structure. The originals are left in place
during the Phase 2 / Phase 3 rollout so:

- If something breaks, the old files are still authoritative.
- A second run of this script is a no-op for already-migrated dates
  (skips when `daily/<date>/sessions.md` already exists with matching
  content).
- Cleanup of the original `daily/<date>.md` files is deferred to a
  later cleanup script (Phase 4) once the digest-pass writes a new
  curated root file at the same path.

Why copy-not-move: the root path `daily/<date>.md` will eventually
hold the Phase 3 digest. Until then, leaving the original keeps the
operator's "todays-daily" workflow intact.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def migrate(vault: Path, *, dry_run: bool) -> tuple[int, int, int]:
    """Walk `<vault>/daily/`, migrate each flat `<date>.md` into `<date>/sessions.md`.

    Returns (migrated, skipped_already_done, skipped_not_a_daily).
    """
    daily_dir = vault / "daily"
    if not daily_dir.is_dir():
        print(f"  no daily/ folder at {daily_dir} — nothing to migrate", file=sys.stderr)
        return (0, 0, 0)

    migrated = 0
    skipped_done = 0
    skipped_other = 0

    for entry in sorted(daily_dir.iterdir()):
        if not entry.is_file():
            continue
        if not _ISO_DATE_RE.match(entry.name):
            skipped_other += 1
            continue
        date_stem = entry.stem  # "2026-05-14"
        target_dir = daily_dir / date_stem
        target_file = target_dir / "sessions.md"

        if target_file.exists():
            if target_file.read_text(encoding="utf-8") == entry.read_text(encoding="utf-8"):
                skipped_done += 1
                continue
            # Content differs — somebody already started using the new structure.
            # Don't clobber; flag for operator review.
            print(f"  CONFLICT: {target_file} exists with different content — skipping {entry.name}", file=sys.stderr)
            skipped_other += 1
            continue

        if dry_run:
            print(f"  DRY: would copy {entry.name} → {date_stem}/sessions.md ({entry.stat().st_size} bytes)")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file.write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  copied {entry.name} → {date_stem}/sessions.md")
        migrated += 1

    return (migrated, skipped_done, skipped_other)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", required=True, type=Path,
                    help="Vault root (the folder that contains daily/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen; write nothing")
    args = ap.parse_args()

    if not args.vault.is_dir():
        print(f"error: --vault {args.vault} is not a directory", file=sys.stderr)
        return 2

    print(f"migrate-daily: vault={args.vault} dry_run={args.dry_run}")
    migrated, skipped_done, skipped_other = migrate(args.vault, dry_run=args.dry_run)
    print(f"\n  migrated:  {migrated}")
    print(f"  already-done (idempotent skip):  {skipped_done}")
    print(f"  non-daily files / conflicts:     {skipped_other}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
