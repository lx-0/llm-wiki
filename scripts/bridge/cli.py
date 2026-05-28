"""CLI entry point for `wiki bridge`.

Subcommands:
- `sync`  : run every configured inbox-bridge mapping
- `--list`: print the configured mappings + resolved local paths
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _setup_logging() -> None:
    from core.paths import LOGS_DIR

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console)

    file_handler = logging.FileHandler(LOGS_DIR / "bridge.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(file_handler)


def _list_mappings() -> NoReturn:
    from core.config import CONFIG

    mappings = CONFIG.personal.inbox_bridges
    if not mappings:
        print("no inbox bridges configured (personal.inbox_bridges is empty)")
        print("see `wiki bridge --help` for the config shape")
        sys.exit(0)

    print(f"{'NAME':<28} {'MODE':<6} {'EN':<3} REMOTE -> LOCAL")
    print("─" * 100)
    for m in mappings:
        from bridge.drive_sync import _mapping_name  # type: ignore

        name = _mapping_name(m) if isinstance(m, dict) else "<invalid>"
        if not isinstance(m, dict):
            print(f"{name:<28} {'?':<6} {'?':<3} (mapping is not a dict)")
            continue
        mode = str(m.get("mode", "move"))[:6]
        enabled = "y" if m.get("enabled", True) else "n"
        remote = str(m.get("remote", "?"))
        local = str(m.get("local", "?"))
        print(f"{name:<28} {mode:<6} {enabled:<3} {remote}")
        print(f"{'':<28} {'':<6} {'':<3}  -> {local}")
    sys.exit(0)


def _run_sync(dry_run: bool) -> NoReturn:
    from bridge.drive_sync import run
    from core.config import CONFIG

    mappings = CONFIG.personal.inbox_bridges
    if not mappings:
        print("no inbox bridges configured (personal.inbox_bridges is empty) — nothing to do")
        sys.exit(0)

    summary = run(mappings, dry_run=dry_run)

    for r in summary.results:
        marker = {"ok": "✓", "skipped": "—", "failed": "✗"}.get(r.status, "?")
        if r.reason:
            print(f"  {marker} {r.name}: {r.status} ({r.reason})")
        else:
            print(f"  {marker} {r.name}: {r.status}")

    print(
        f"\n{summary.ok_count} ok · {summary.skipped_count} skipped · "
        f"{summary.failed_count} failed"
    )
    sys.exit(summary.exit_code)


def main() -> NoReturn:
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="wiki bridge",
        description="rsync-based mirror for sandbox-restricted intake folders",
    )
    sub = parser.add_subparsers(dest="cmd")

    sync_p = sub.add_parser("sync", help="mirror every configured inbox bridge")
    sync_p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what rsync would do without copying / removing anything",
    )

    sub.add_parser("list", help="print configured mappings")

    args = parser.parse_args()

    if args.cmd in (None, "list"):
        _list_mappings()
    if args.cmd == "sync":
        _run_sync(dry_run=args.dry_run)

    parser.error(f"unknown subcommand: {args.cmd}")


if __name__ == "__main__":
    main()
