"""One-shot cleanup for curiosity-loop deep-scan empty outputs.

Background: between 2026-05-13 (curiosity-loop consumer landed) and the
2026-05-16 ThunderbirdMboxReader alias-resolution fix, every curiosity
request that targeted a `kasserver/INBOX/...` folder hit a silent
folder-name mismatch (`INBOX-1.sbd/` on disk vs `INBOX/...` in config)
and wrote an empty `raw/notes/email/deep-*.md` file with
`messages: 0`. The corresponding request JSON was flipped to
`status: done` so the consumer never re-attempted it.

This script:
  1. Deletes empty deep-scan output files (frontmatter `messages: 0` AND
     `origin: curiosity/email-deep-scan` — never touches the older
     thunderbird-deep-scan format which had real content).
  2. Flips `status: done` requests with `messages_pulled: 0` back to
     `status: pending` so the alias-fixed consumer reprocesses them.

Run AFTER deploying the adapter fix; idempotent.

Usage:
    uv run python scripts/migrations/cleanup_empty_deep_scans.py --vault PATH            # preview
    uv run python scripts/migrations/cleanup_empty_deep_scans.py --vault PATH --apply    # write
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("cleanup-empty-deep-scans")

# Frontmatter signature for curiosity-loop output. Matches the strict
# pair (origin tag + zero-message marker) to avoid deleting other
# deep-scan formats that happen to have 0 messages legitimately.
_ORIGIN_RE = re.compile(r'^origin:\s*"?curiosity/email-deep-scan"?\s*$', re.MULTILINE)
_MESSAGES_RE = re.compile(r'^messages:\s*0\s*$', re.MULTILINE)


def find_empty_outputs(deep_scan_dir: Path) -> list[Path]:
    """Return deep-*.md files written by curiosity-loop with messages: 0."""
    out: list[Path] = []
    if not deep_scan_dir.exists():
        return out
    for path in sorted(deep_scan_dir.glob("deep-*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Could not read %s: %s", path.name, exc)
            continue
        # Read only the leading frontmatter block (first ~30 lines covers it).
        head = "\n".join(text.splitlines()[:30])
        if _ORIGIN_RE.search(head) and _MESSAGES_RE.search(head):
            out.append(path)
    return out


def find_done_zero_requests(requests_dir: Path) -> list[Path]:
    """Return request JSONs marked done with 0 messages pulled."""
    out: list[Path] = []
    if not requests_dir.exists():
        return out
    for path in sorted(requests_dir.glob("request-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not parse %s: %s", path.name, exc)
            continue
        if data.get("status") == "done" and data.get("messages_pulled", 0) == 0:
            out.append(path)
    return out


def reset_to_pending(path: Path) -> None:
    """Flip a done-zero request back to pending so the fixed consumer retries.

    Strips processed_at / output / messages_pulled so the state is clean.
    Adds a `reprocess_reason` breadcrumb pointing at the 2026-05-16 fix.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "pending"
    for k in ("processed_at", "output", "messages_pulled"):
        data.pop(k, None)
    data["reprocess_reason"] = (
        "2026-06-10: previous run hit the head-only/case-insensitive "
        "folder check in ThunderbirdMboxReader (legacy POP root vetoed "
        "INBOX-N alias resolution) and wrote an empty deep-scan; "
        "full-path case-sensitive resolution shipped, retry."
    )
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", required=True, help="Vault root path")
    parser.add_argument("--apply", action="store_true", help="write changes (default: preview)")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        log.error("Vault not found: %s", vault)
        return 1

    deep_scan_dir = vault / "raw" / "notes" / "email"
    requests_dir = vault / "raw" / "requests"

    empty_files = find_empty_outputs(deep_scan_dir)
    done_requests = find_done_zero_requests(requests_dir)

    log.info("Vault: %s", vault)
    log.info("Empty curiosity deep-scans to delete: %d", len(empty_files))
    for f in empty_files:
        log.info("  - %s", f.relative_to(vault))
    log.info("Done-with-0-messages requests to reset → pending: %d", len(done_requests))
    for f in done_requests:
        log.info("  - %s", f.relative_to(vault))

    if not args.apply:
        log.info("Preview only. Re-run with --apply to write.")
        return 0

    for f in empty_files:
        f.unlink()
        log.info("Deleted %s", f.relative_to(vault))
    for f in done_requests:
        reset_to_pending(f)
        log.info("Reset → pending: %s", f.relative_to(vault))

    log.info("Done. %d files deleted, %d requests reset.", len(empty_files), len(done_requests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
