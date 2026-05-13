"""CLI entry-point for `wiki curiosity`.

Usage:
    uv run python scripts/curiosity/cli.py --list                 list pending requests
    uv run python scripts/curiosity/cli.py --run-oldest           run the oldest pending request
    uv run python scripts/curiosity/cli.py --run <slug>           run one by slug or filename
    uv run python scripts/curiosity/cli.py --run-all              run every pending request
    uv run python scripts/curiosity/cli.py --dry-run --run-oldest plan only, no scan
    uv run python scripts/curiosity/cli.py --clear-done           delete done request files

Requests live as `raw/requests/request-<slug>-<date>.json`. The producer
(`scripts/curiosity/producer.py`, invoked from `compile.py`) writes them;
this CLI is the consumer side.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ROOT_DIR
from curiosity.backends import email as email_backend

REQUESTS_DIR = ROOT_DIR / "raw" / "requests"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("curiosity")


def _all_requests() -> list[Path]:
    if not REQUESTS_DIR.exists():
        return []
    return sorted(REQUESTS_DIR.glob("request-*.json"))


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _list() -> NoReturn:
    rows = []
    for p in _all_requests():
        r = _read(p)
        if r is None:
            rows.append((p.name, "?", "?", "?", "(unreadable)"))
            continue
        rows.append((
            p.name,
            r.get("type", "?"),
            r.get("status", "?"),
            r.get("account", "?"),
            r.get("topic", "")[:50],
        ))
    if not rows:
        print("No curiosity requests in raw/requests/.")
        sys.exit(0)
    print(f"{'FILE':<55} {'TYPE':<20} {'STATUS':<10} {'ACCOUNT':<12} TOPIC")
    print("─" * 130)
    for fn, t, st, acc, topic in rows:
        print(f"{fn:<55} {t:<20} {st:<10} {acc:<12} {topic}")
    sys.exit(0)


def _dispatch(request_path: Path, *, dry_run: bool) -> bool:
    r = _read(request_path)
    if r is None:
        log.error("Could not read %s", request_path.name)
        return False
    kind = r.get("type")
    if kind == "email-deep-scan":
        result = email_backend.process_request(request_path, dry_run=dry_run)
        return result.success
    log.error("Unsupported request type %r in %s — no backend wired", kind, request_path.name)
    return False


def _run_one(slug_or_name: str, *, dry_run: bool) -> NoReturn:
    candidates = _all_requests()
    if not candidates:
        log.error("No curiosity requests in raw/requests/.")
        sys.exit(1)
    matches = [p for p in candidates if slug_or_name in p.stem]
    if not matches:
        log.error("No request matched %r. Use --list to see all.", slug_or_name)
        sys.exit(1)
    if len(matches) > 1:
        log.error("Ambiguous: %d matches for %r (%s). Be more specific.",
                  len(matches), slug_or_name, ", ".join(p.name for p in matches))
        sys.exit(1)
    ok = _dispatch(matches[0], dry_run=dry_run)
    sys.exit(0 if ok else 2)


def _run_oldest(*, dry_run: bool) -> NoReturn:
    pending = email_backend.list_pending(REQUESTS_DIR)
    if not pending:
        log.info("No pending curiosity requests.")
        sys.exit(0)
    target = pending[0]
    log.info("Running oldest pending: %s", target.name)
    ok = _dispatch(target, dry_run=dry_run)
    sys.exit(0 if ok else 2)


def _run_all(*, dry_run: bool) -> NoReturn:
    pending = email_backend.list_pending(REQUESTS_DIR)
    if not pending:
        log.info("No pending curiosity requests.")
        sys.exit(0)
    log.info("Running %d pending request(s)…", len(pending))
    fails = 0
    for p in pending:
        log.info("→ %s", p.name)
        if not _dispatch(p, dry_run=dry_run):
            fails += 1
    log.info("Done. %d failed, %d processed.", fails, len(pending) - fails)
    sys.exit(0 if fails == 0 else 2)


def _clear_done() -> NoReturn:
    removed = 0
    for p in _all_requests():
        r = _read(p)
        if r is None:
            continue
        if r.get("status") == "done":
            p.unlink()
            removed += 1
    print(f"Removed {removed} done request file(s).")
    sys.exit(0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Curiosity request consumer — list / run / clear pending requests."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list all requests + statuses")
    group.add_argument("--run-oldest", action="store_true", help="run the oldest pending request")
    group.add_argument("--run", metavar="SLUG", help="run one request by slug substring")
    group.add_argument("--run-all", action="store_true", help="run every pending request")
    group.add_argument("--clear-done", action="store_true", help="delete request files with status: done")
    parser.add_argument("--dry-run", action="store_true", help="plan only, do not touch the mailbox or write output")
    args = parser.parse_args()

    if args.list:
        _list()
    if args.clear_done:
        _clear_done()
    if args.run_oldest:
        _run_oldest(dry_run=args.dry_run)
    if args.run_all:
        _run_all(dry_run=args.dry_run)
    if args.run:
        _run_one(args.run, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
