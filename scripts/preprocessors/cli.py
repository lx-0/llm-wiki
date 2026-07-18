"""CLI entry-point for `wiki preprocess`. Bash dispatcher in `wiki` shells here.

Two modes:
- `--list`: enumerate registered Preprocessors with their output subfolder.
- `<name> [source] [--dry-run]`: run one Preprocessor. `source` is required for
  preprocessors whose SPEC.takes_source is True (today: `html`), ignored by the
  folder-sweep singletons (`inbox`, `clippings`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _list() -> NoReturn:
    from preprocessors import all_preprocessors

    print(f"{'NAME':<14} {'OUTPUT':<20} SOURCE-ARG")
    print("─" * 60)
    for p in all_preprocessors():
        spec = p.SPEC
        src = "required" if spec.takes_source else "(none — sweep)"
        print(f"{spec.name:<14} {spec.output_subfolder:<20} {src}")
    sys.exit(0)


def _run_one(name: str, *, dry_run: bool, source: str | None) -> NoReturn:
    from preprocessors import get_preprocessor

    pre = get_preprocessor(name)
    if pre is None:
        print(f"error: no preprocessor registered with name {name!r}", file=sys.stderr)
        print("       try: wiki preprocess --list", file=sys.stderr)
        sys.exit(1)

    if pre.SPEC.takes_source and not source:
        print(f"error: preprocessor {name!r} needs a source (path or URL)", file=sys.stderr)
        sys.exit(1)

    result = pre.run(dry_run=dry_run, source=source)
    print(result.message)
    print(f"  files written: {len(result.files_written)}")
    if result.files_skipped:
        print(f"  files skipped: {result.files_skipped}")
    if result.errors:
        print(f"  errors: {len(result.errors)}", file=sys.stderr)
        for err in result.errors:
            print(f"    ✗ {err}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _setup_logging() -> None:
    """Console (stderr, terse) + a persistent file. Mirrors collectors/cli.py."""
    from core.paths import LOGS_DIR

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console)

    file_handler = logging.FileHandler(LOGS_DIR / "preprocessors.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(file_handler)


def main() -> NoReturn:
    _setup_logging()

    parser = argparse.ArgumentParser(prog="wiki preprocess")
    parser.add_argument("--list", action="store_true", help="enumerate registered preprocessors")
    parser.add_argument("name", nargs="?", help="preprocessor name (omit with --list)")
    parser.add_argument("source", nargs="?", help="source path/URL (only for takes_source preprocessors)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.list:
        _list()
    if args.name is None:
        parser.error("missing preprocessor name (or pass --list)")
    _run_one(args.name, dry_run=args.dry_run, source=args.source)


if __name__ == "__main__":
    main()
