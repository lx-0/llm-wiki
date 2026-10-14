"""CLI entry-point for `wiki produce`. Bash dispatcher in `wiki` shells here.

Two modes:
- `--list`: enumerate registered Producers with their declared gates.
- `<name> <source>`: run one Producer on one source path (operator-invoked
  re-run / debug / replay; the production driver is compile.py's per-file
  loop via producers.orchestrate.evaluate_and_run).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import NoReturn

from core.console import setup_console_logging
from core.paths import LOGS_DIR


def _list() -> NoReturn:
    from producers import all_producers

    print(f"{'NAME':<14} {'ENABLED-KEY':<40} GLOB-KEY")
    print("─" * 100)
    for p in all_producers():
        spec = p.SPEC
        enabled = spec.enabled_config_key or "(always)"
        globs = spec.source_glob_config_key or "(any source)"
        print(f"{spec.name:<14} {enabled:<40} {globs}")
    sys.exit(0)


def _run_one(name: str, source: Path) -> NoReturn:
    from core.paths import ROOT_DIR
    from producers import get_producer
    from producers.orchestrate import evaluate_and_run

    producer = get_producer(name)
    if producer is None:
        print(f"error: no producer registered with name {name!r}", file=sys.stderr)
        print("       try: wiki produce --list", file=sys.stderr)
        sys.exit(1)

    # Producers' internal logic computes `source.relative_to(ROOT_DIR)`.
    # That requires an absolute path; operator-supplied vault-relative
    # paths (`raw/memories/x.md`) would otherwise raise ValueError. The
    # production compile loop hands absolute paths via `list_raw_files()`;
    # the CLI normalizes to the same shape.
    if not source.is_absolute():
        source = (ROOT_DIR / source).resolve()

    if not source.exists():
        print(f"error: source path does not exist: {source}", file=sys.stderr)
        sys.exit(1)

    result = asyncio.run(evaluate_and_run(producer, source))

    print(f"{result.producer}: {result.status}")
    if result.reason:
        print(f"  reason: {result.reason}")
    if result.outputs:
        print(f"  outputs ({len(result.outputs)}):")
        for out in result.outputs:
            print(f"    {out}")

    sys.exit(0 if result.status != "failed" else 1)


def main() -> NoReturn:
    # Console + `logs/producers.log`: an operator-invoked replay leaves a trace even
    # when stdout/stderr were routed to DEVNULL.
    setup_console_logging("producers", log_file=LOGS_DIR / "producers.log")

    parser = argparse.ArgumentParser(prog="wiki produce")
    parser.add_argument("--list", action="store_true", help="enumerate registered producers")
    parser.add_argument("name", nargs="?", help="producer name (omit with --list)")
    parser.add_argument("source", nargs="?", help="source path to run the producer on")
    args = parser.parse_args()

    if args.list:
        _list()
    if args.name is None or args.source is None:
        parser.error("missing producer name + source (or pass --list)")
    _run_one(args.name, Path(args.source))


if __name__ == "__main__":
    main()
