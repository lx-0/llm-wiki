"""`wiki collect` — the one verb for the collectors (cli.py runs this as the handler).

Three modes:
- `--list [--json]`: enumerate registered Collectors with config status
- `<name> [--dry-run] [--incremental] [--account ID]`: run one Collector (the Registry run)
- `<name> -- <flags>`: the collector module's own CLI, `main(argv)` — screenshots'
  `--backfill` / `--limit` / …, browser's `--source`, tabs' `--backup-dir`, youtube's `--url`.
  It replaced three by-path entry scripts (M034-S06-T04).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import NoReturn

from core.console import say, setup_console_logging
from core.paths import LOGS_DIR


def _list(as_json: bool = False) -> NoReturn:
    from collectors import all_collectors

    if as_json:
        # Machine-readable seam (same posture as `wiki doctor --json` /
        # `wiki menu --json`): GUI + agent consumers read this instead of
        # scraping the human table's ✓/✗ glyph column.
        payload = {
            "collectors": [
                {
                    "name": c.SPEC.name,
                    "configured": c.is_configured(),
                    "output": c.SPEC.output_subfolder,
                    "piggyback": "auto" if c.SPEC.piggyback_default else "manual-only",
                }
                for c in all_collectors()
            ]
        }
        say(json.dumps(payload, indent=2))
        sys.exit(0)

    say(f"{'NAME':<20} {'CONFIGURED':<18} {'OUTPUT':<28} PIGGYBACK")
    say("─" * 90)
    for c in all_collectors():
        spec = c.SPEC
        cfg = "✓" if c.is_configured() else "✗"
        pb = "auto" if spec.piggyback_default else "manual-only"
        say(f"{spec.name:<20} {cfg:<18} {spec.output_subfolder:<28} {pb}")
    sys.exit(0)


def _run_one(name: str, *, dry_run: bool, incremental: bool, account: str | None) -> NoReturn:
    from collectors import get_collector

    collector = get_collector(name)
    if collector is None:
        say(f"error: no collector registered with name {name!r}", file=sys.stderr)
        say("       try: wiki collect --list", file=sys.stderr)
        sys.exit(1)

    if not collector.is_configured():
        say(f"warning: collector {name!r} is not configured — running anyway")

    # `--account` restricts the run to one account id. It only applies to
    # account substrates (SPEC.supports_account_loop) — the field's real
    # consumer. A singleton collector (browser, screenshots, …) that got an
    # --account flag is an operator error, surfaced loudly rather than
    # silently ignored.
    if account is not None:
        if not collector.SPEC.supports_account_loop:
            say(
                f"error: collector {name!r} does not support --account (not an account substrate)",
                file=sys.stderr,
            )
            say(
                "       --account applies only to account substrates "
                "(email, calendar, gmeet, jamie, health)",
                file=sys.stderr,
            )
            sys.exit(1)
        result = collector.run(dry_run=dry_run, incremental=incremental, account=account)
    else:
        result = collector.run(dry_run=dry_run, incremental=incremental)
    say(result.message)
    say(f"  files written: {len(result.files_written)}")
    say(f"  files skipped: {result.files_skipped}")
    if result.errors:
        # Surface scan failures loudly + exit non-zero — a piggyback run's
        # output is DEVNULL'd by flush.py, but the FileHandler keeps a trace
        # and the exit code lets any wrapper detect the failure.
        say(f"  errors: {len(result.errors)}", file=sys.stderr)
        for err in result.errors:
            say(f"    ✗ {err}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _split_tail(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """`wiki collect`'s own arguments, and everything after the first `--` (the collector's
    own flags, passed on untouched — a later `--` included), or None without one."""
    if "--" not in argv:
        return argv, None
    i = argv.index("--")
    return argv[:i], argv[i + 1 :]


def _run_direct(name: str, argv: list[str]) -> NoReturn:
    """`wiki collect <name> -- <flags>`: the collector module's own CLI, its `main(argv)`.
    The module is imported alone (`collectors.MODULES`, M034-S06-T03); its exit code is the
    command's."""
    from collectors import MODULES

    module = MODULES.get(name)
    if module is None:
        say(f"error: no collector registered with name {name!r}", file=sys.stderr)
        say("       try: wiki collect --list", file=sys.stderr)
        sys.exit(1)
    main_of = getattr(importlib.import_module(module), "main", None)
    if main_of is None:
        own = [n for n, m in MODULES.items() if hasattr(importlib.import_module(m), "main")]
        say(f"error: collector {name!r} has no flags of its own", file=sys.stderr)
        say(f"       `--` passes flags to: {', '.join(own)}", file=sys.stderr)
        sys.exit(1)
    sys.exit(main_of(argv) or 0)


def main() -> NoReturn:
    # Console + `logs/collectors.log`: piggyback collector runs are spawned by
    # `flush.py` with stdout/stderr routed to DEVNULL — the file is their only trace.
    setup_console_logging("collectors", log_file=LOGS_DIR / "collectors.log")

    own, tail = _split_tail(sys.argv[1:])
    parser = argparse.ArgumentParser(prog="wiki collect")
    parser.add_argument("--list", action="store_true", help="enumerate registered collectors")
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --list: machine-readable output (desktop app / agents)",
    )
    parser.add_argument("name", nargs="?", help="collector name (omit with --list)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--account", default=None)
    args = parser.parse_args(own)

    if args.json and not args.list:
        parser.error("--json requires --list")
    if tail is not None:
        if args.list or args.name is None:
            parser.error("`--` passes flags to one collector: wiki collect <name> -- <flags>")
        if args.dry_run or args.incremental or args.account is not None:
            parser.error(
                "--dry-run / --incremental / --account are the Registry run's; with `--`, "
                "pass the collector's own flags after it"
            )
        _run_direct(args.name, tail)
    if args.list:
        _list(as_json=args.json)
    if args.name is None:
        parser.error("missing collector name (or pass --list)")
    _run_one(args.name, dry_run=args.dry_run, incremental=args.incremental, account=args.account)


if __name__ == "__main__":
    main()
