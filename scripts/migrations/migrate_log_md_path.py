"""Migrate `<vault>/knowledge/log.md` to `<vault>/.wiki/logs/operations.md`.

Pre-2026-05-28, the engine's operations log lived at `knowledge/log.md` —
inside Obsidian's index. On vaults with heavy compile + dream history the
file grew past 2 MB (lxw: 2 MB / ~15k lines) and crashed Obsidian on open.
The log is engine telemetry, not a knowledge article, so it now lives at
`.wiki/logs/operations.md` (Obsidian-invisible, alongside the other engine
logs).

Idempotent: re-running after a successful migration finds nothing to do.
Graceful: handles both the live filename (`knowledge/log.md`) and the
quarantine name the lxw operator used on 2026-05-28
(`knowledge/.log.md.disabled-test`). If both source and destination exist,
prepends the source content to the destination (source is older, dest is
newer) and leaves a `.migrated-<ts>` audit copy of the source.

Usage:
    uv run --project .wiki python scripts/migrations/migrate_log_md_path.py
    uv run --project .wiki python scripts/migrations/migrate_log_md_path.py --dry-run
    uv run --project .wiki python scripts/migrations/migrate_log_md_path.py --vault /path/to/vault
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-log-md-path")


# Candidate source filenames under <vault>/knowledge/, in priority order.
# `log.md` is the canonical pre-migration name. `.log.md.disabled-test` is
# the quarantine name an operator used on 2026-05-28 to stop Obsidian from
# crashing while still preserving the history.
SOURCE_CANDIDATES = ("log.md", ".log.md.disabled-test")


def migrate(vault: Path, dry_run: bool) -> int:
    knowledge = vault / "knowledge"
    dest_dir = vault / ".wiki" / "logs"
    dest = dest_dir / "operations.md"

    sources = [knowledge / name for name in SOURCE_CANDIDATES if (knowledge / name).exists()]
    if not sources:
        log.info("Nothing to migrate — no knowledge/log.md (or quarantine variant) found at %s", knowledge)
        return 0

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for src in sources:
        src_text = src.read_text(encoding="utf-8")
        src_size = src.stat().st_size

        if dest.exists():
            dest_text = dest.read_text(encoding="utf-8")
            # Source is older history; prepend it under the existing header.
            # If both start with "# Operations Log", strip the duplicate header.
            stripped_src = src_text
            if stripped_src.lstrip().startswith("# Operations Log"):
                # drop the first header line + trailing blank line
                first_nl = stripped_src.find("\n")
                if first_nl != -1:
                    stripped_src = stripped_src[first_nl + 1 :].lstrip("\n")
            if dest_text.lstrip().startswith("# Operations Log"):
                head, _, rest = dest_text.partition("\n")
                merged = f"{head}\n\n{rest.lstrip()}\n{stripped_src}"
            else:
                merged = f"# Operations Log\n\n{dest_text.lstrip()}\n{stripped_src}"
            audit = src.with_suffix(src.suffix + f".migrated-{datetime.now().strftime('%Y%m%dT%H%M%S')}")
            if dry_run:
                log.info("would merge %s (%d bytes) into existing %s, leaving audit copy %s",
                         src, src_size, dest, audit.name)
            else:
                dest.write_text(merged, encoding="utf-8")
                src.rename(audit)
                log.info("merged %s (%d bytes) into %s; audit copy at %s", src, src_size, dest, audit)
        else:
            if dry_run:
                log.info("would move %s (%d bytes) → %s", src, src_size, dest)
            else:
                shutil.move(str(src), str(dest))
                log.info("moved %s (%d bytes) → %s", src, src_size, dest)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate knowledge/log.md → .wiki/logs/operations.md")
    parser.add_argument("--vault", type=Path, default=None,
                        help="Vault root (default: derive from this file's location)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    args = parser.parse_args(argv)

    if args.vault is not None:
        vault = args.vault.expanduser().resolve()
    else:
        # scripts/migrations/<this>.py → vault = <this>/../../.. (engine in .wiki/scripts/migrations/)
        vault = Path(__file__).resolve().parent.parent.parent.parent

    if not (vault / "knowledge").exists():
        log.warning("Vault has no knowledge/ dir at %s — skipping", vault)
        return 0

    if args.dry_run:
        log.info("=== DRY RUN — no files will be moved ===")

    return migrate(vault, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
