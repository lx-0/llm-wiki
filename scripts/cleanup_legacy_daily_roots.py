"""One-shot cleanup: remove legacy flat `daily/<date>.md` files whose content
is preserved in `daily/<date>/sessions.md` (post-migration state).

The migration script (`migrate_daily_to_rollup.py`) COPIES instead of moves
during the dual-state window — originals stay alive while the new subfolder
fills up. Once the operator is satisfied the new structure works, this
cleanup removes the duplicates.

Safety:
- For each `daily/<date>.md`, this script reads BOTH the root file and
  `daily/<date>/sessions.md` and refuses to delete unless their contents
  byte-match exactly. Operator-edits post-migration produce a content
  divergence → refusal + report.
- Frontmatter-equipped digests (`type: daily-digest`) are also refused —
  those are LATER artefacts (compile-stage digests), not legacy flat
  dailies. Detection via `_FRONTMATTER_RE`.
- Today's date is skipped (active session may be writing).
- Idempotent: re-running on an already-cleaned vault is a no-op.

Usage:
    uv run python scripts/cleanup_legacy_daily_roots.py --vault <path> [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date as _date
from pathlib import Path

log = logging.getLogger("cleanup_legacy_daily_roots")

_ISO_MD_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _has_digest_frontmatter(text: str) -> bool:
    """True if the root file already carries `type: daily-digest` — keep it."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return False
    block = m.group(1)
    return re.search(r"^type:\s*daily-digest\b", block, re.MULTILINE) is not None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s",
                        datefmt="%H:%M:%S")

    if not args.vault.is_dir():
        print(f"error: --vault {args.vault} is not a directory", file=sys.stderr)
        return 2

    daily_root = args.vault / "daily"
    if not daily_root.is_dir():
        print(f"  no daily/ folder at {daily_root} — nothing to clean", file=sys.stderr)
        return 0

    today_iso = _date.today().isoformat()

    deleted = 0
    skipped_today = 0
    skipped_digest = 0
    skipped_no_subfolder = 0
    skipped_diverged = 0
    diverged_paths: list[str] = []

    for entry in sorted(daily_root.iterdir()):
        if not entry.is_file():
            continue
        m = _ISO_MD_RE.match(entry.name)
        if not m:
            continue
        date_iso = m.group(1)

        if date_iso == today_iso:
            skipped_today += 1
            continue

        sessions_file = daily_root / date_iso / "sessions.md"
        if not sessions_file.is_file():
            skipped_no_subfolder += 1
            continue

        try:
            root_bytes = entry.read_bytes()
            sub_bytes = sessions_file.read_bytes()
        except OSError as e:
            log.warning("  %s: read failed — %s", entry.name, e)
            continue

        # Don't delete a real digest (post-cleanup operator might re-run this).
        try:
            root_text = root_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            root_text = ""
        if _has_digest_frontmatter(root_text):
            skipped_digest += 1
            continue

        if root_bytes != sub_bytes:
            skipped_diverged += 1
            diverged_paths.append(entry.name)
            log.warning("  %s: content diverges from daily/%s/sessions.md — refusing to delete",
                        entry.name, date_iso)
            continue

        if args.dry_run:
            log.info("  DRY: would delete %s (%d bytes, matches subfolder)",
                     entry.name, len(root_bytes))
        else:
            entry.unlink()
            log.info("  deleted %s", entry.name)
        deleted += 1

    log.info("")
    log.info("cleanup totals (vault=%s, dry_run=%s):", args.vault, args.dry_run)
    log.info("  %s legacy roots:      %d", "would delete" if args.dry_run else "deleted", deleted)
    log.info("  skipped (today):           %d", skipped_today)
    log.info("  skipped (real digest):     %d", skipped_digest)
    log.info("  skipped (no subfolder):    %d", skipped_no_subfolder)
    log.info("  skipped (diverged):        %d  %s",
             skipped_diverged, f"— {diverged_paths}" if diverged_paths else "")
    if skipped_diverged:
        log.warning("Diverged files need operator review. Either:")
        log.warning("  (a) accept the subfolder version as canonical → manually remove root,")
        log.warning("  (b) merge the diverged root edits into daily/<date>/sessions.md by hand,")
        log.warning("  (c) leave both in place — the divergence will surface as a daily_root_not_digest lint warning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
