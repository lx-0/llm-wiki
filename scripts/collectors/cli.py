"""CLI entry-point for `wiki collect`. Bash dispatcher in `wiki` shells here.

Two modes:
- `--list`: enumerate registered Collectors with config status
- `<name> [--dry-run] [--incremental] [--account ID]`: run one Collector
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _list() -> NoReturn:
    from collectors import all_collectors

    print(f"{'NAME':<20} {'CONFIGURED':<18} {'OUTPUT':<28} PIGGYBACK")
    print("─" * 90)
    for c in all_collectors():
        spec = c.SPEC
        cfg = "✓" if c.is_configured() else "✗"
        pb = "auto" if spec.piggyback_default else "manual-only"
        print(f"{spec.name:<20} {cfg:<18} {spec.output_subfolder:<28} {pb}")
    sys.exit(0)


def _run_one(name: str, *, dry_run: bool, incremental: bool, account: str | None) -> NoReturn:
    from collectors import get_collector

    collector = get_collector(name)
    if collector is None:
        print(f"error: no collector registered with name {name!r}", file=sys.stderr)
        print("       try: wiki collect --list", file=sys.stderr)
        sys.exit(1)

    if not collector.is_configured():
        print(f"warning: collector {name!r} is not configured — running anyway")

    # The base `run()` Protocol takes only dry_run + incremental. Account
    # filtering lives in CONFIG today (operators pass `--account work` to
    # restrict, but the Collector currently iterates *all* accounts that
    # resolve to a Reader). We honor `--account` by setting an env var
    # the Collector can opt into reading; today EmailCollector ignores
    # it, that's a S02 follow-up. Logged for visibility.
    if account is not None:
        print(f"note: --account={account} is parsed but not yet honored by EmailCollector (S02 task)")

    result = collector.run(dry_run=dry_run, incremental=incremental)
    print(result.message)
    print(f"  files written: {len(result.files_written)}")
    print(f"  files skipped: {result.files_skipped}")
    sys.exit(0)


def main() -> NoReturn:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(prog="wiki collect")
    parser.add_argument("--list", action="store_true", help="enumerate registered collectors")
    parser.add_argument("name", nargs="?", help="collector name (omit with --list)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--account", default=None)
    args = parser.parse_args()

    if args.list:
        _list()
    if args.name is None:
        parser.error("missing collector name (or pass --list)")
    _run_one(args.name, dry_run=args.dry_run, incremental=args.incremental, account=args.account)


if __name__ == "__main__":
    main()
