"""CLI entry-point for `wiki curiosity`.

Usage:
    uv run python scripts/curiosity/cli.py                        interactive walk (default)
    uv run python scripts/curiosity/cli.py --list                 list pending requests
    uv run python scripts/curiosity/cli.py --run-oldest           run the oldest pending request (non-interactive)
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

from core.console import read_key
from core.paths import ROOT_DIR
from core.utils import now_iso
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


def _run_batch(n: int, *, dry_run: bool) -> NoReturn:
    """Process the N oldest pending requests in one invocation.

    Used by the `curiosity_followup` flush-piggyback to drain the
    backlog at a steady rate (cooldown × N per day) without the
    thundering-herd risk of `--run-all` on accumulated backlogs.
    """
    pending = email_backend.list_pending(REQUESTS_DIR)
    if not pending:
        log.info("No pending curiosity requests.")
        sys.exit(0)
    batch = pending[:n]
    log.info("Running batch of %d (of %d pending total)…", len(batch), len(pending))
    fails = 0
    for p in batch:
        log.info("→ %s", p.name)
        if not _dispatch(p, dry_run=dry_run):
            fails += 1
    log.info(
        "Batch done. %d failed, %d processed, %d still pending.",
        fails, len(batch) - fails, len(pending) - len(batch),
    )
    sys.exit(0 if fails == 0 else 2)


def _print_request_card(idx: int, total: int, path: Path, r: dict) -> None:
    """Pretty-print one pending request for the walk prompt."""
    bar = "─" * 78
    print()
    print(bar)
    print(f"  [{idx}/{total}]  {path.name}")
    print(bar)
    print(f"  Topic       : {r.get('topic', '?')}")
    print(f"  Folder      : {r.get('folder', '?')}   (confidence {r.get('folder_confidence', '?')}/5)")
    print(f"  Account     : {r.get('account', '?')}")
    print(f"  Source      : {r.get('source', '?')}")
    print(f"  Created     : {r.get('created', '?')}")
    print(f"  Model       : {r.get('model', '?')}")
    print()
    quote = r.get("source_quote", "").strip()
    if quote:
        print("  Source quote:")
        for line in quote.splitlines() or [quote]:
            print(f"    > {line}")
    rationale = r.get("rationale", "").strip()
    if rationale:
        print()
        print("  Why this folder:")
        for line in rationale.splitlines() or [rationale]:
            print(f"    {line}")
    print()


def _mark_rejected(path: Path, r: dict) -> None:
    r["status"] = "rejected"
    r["rejected_at"] = now_iso()
    path.write_text(json.dumps(r, indent=2), encoding="utf-8")


def _walk(*, dry_run: bool) -> NoReturn:
    """Interactive walk over pending requests.

    Per item shows the full context (topic, source quote, rationale, folder,
    source) and prompts [a]ccept / [s]kip / [r]eject / [q]uit. Skip leaves
    the request pending (it shows up again next walk). Reject sets
    status=rejected so the producer's persistent-rejection check drops
    future re-emissions of the same slug.
    """
    pending = email_backend.list_pending(REQUESTS_DIR)
    if not pending:
        log.info("No pending curiosity requests.")
        sys.exit(0)

    total = len(pending)
    accepted = skipped = rejected = 0
    fails = 0
    for idx, path in enumerate(pending, start=1):
        r = _read(path)
        if r is None:
            log.error("Skipping unreadable %s", path.name)
            continue
        _print_request_card(idx, total, path, r)

        # Single-keypress prompt — same DRY mechanism the home menu uses
        # (core.console.read_key in cbreak mode). No Enter required.
        print("  [a]ccept · [s]kip · [r]eject · [q]uit › ", end="", flush=True)
        while True:
            try:
                key = read_key()
            except (OSError, KeyboardInterrupt):
                print()
                log.info("Walk aborted. %d accepted, %d skipped, %d rejected, %d remain.",
                         accepted, skipped, rejected, total - idx + 1)
                sys.exit(0)
            if key in ("a", "A"):
                print("a")
                ok = _dispatch(path, dry_run=dry_run)
                accepted += 1
                if not ok:
                    fails += 1
                break
            if key in ("s", "S", "enter"):
                print("s")
                skipped += 1
                break
            if key in ("r", "R"):
                print("r")
                _mark_rejected(path, r)
                rejected += 1
                log.info("Rejected: %s (producer will skip this slug)", r.get("topic", path.name))
                break
            if key in ("q", "Q", "c-c", "c-d", "esc"):
                print("q")
                log.info("Walk ended. %d accepted, %d skipped, %d rejected, %d remain.",
                         accepted, skipped, rejected, total - idx + 1)
                sys.exit(0 if fails == 0 else 2)
            # Unknown key — beep / hint, keep prompting on same line.
            print("\r  [a]ccept · [s]kip · [r]eject · [q]uit › ", end="", flush=True)
    log.info("Walk complete. %d accepted, %d skipped, %d rejected (of %d).",
             accepted, skipped, rejected, total)
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
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--walk", action="store_true", help="interactive walk: accept/skip/reject each pending (default)")
    group.add_argument("--list", action="store_true", help="list all requests + statuses")
    group.add_argument("--run-oldest", action="store_true", help="run the oldest pending request (non-interactive)")
    group.add_argument("--run", metavar="SLUG", help="run one request by slug substring")
    group.add_argument("--run-all", action="store_true", help="run every pending request")
    group.add_argument("--run-batch", metavar="N", type=int, help="run the N oldest pending requests (drain at steady rate)")
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
    if args.run_batch is not None:
        if args.run_batch < 1:
            log.error("--run-batch N requires N >= 1, got %d", args.run_batch)
            sys.exit(2)
        _run_batch(args.run_batch, dry_run=args.dry_run)
    if args.run:
        _run_one(args.run, dry_run=args.dry_run)
    # No subcommand selected → walk
    _walk(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
