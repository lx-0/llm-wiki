"""Daily-digest runner — invokes the `daily-digest` agent via the wiki CLI.

Triggered both manually (`wiki agent daily-digest --var date=YYYY-MM-DD`)
and as the `daily_digest_yesterday` piggyback. This thin wrapper exists
because the piggyback dispatcher (`core/piggybacks.py`) expects a
script-path entry in `_BUILTIN_PIGGYBACK_TASKS`; it resolves `--date
yesterday` to an
ISO date and shells out to `wiki agent daily-digest --var date=<iso>`.

If the target date has no per-source captures (no `daily/<date>/`
subfolder), the runner short-circuits with a no-op log line — agent
invocation is the expensive part.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import TIMEZONE
from core.paths import DAILY_DIR, WIKI_DIR

# A `## Captures` section up to the next `## ` heading or end-of-file.
_CAPTURES_SECTION_RE = re.compile(r"\n*^## Captures$.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)

log = logging.getLogger("daily_digest_runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


def _resolve_date(arg: str) -> str:
    """`yesterday` / `today` shortcuts + raw ISO passthrough."""
    arg = arg.strip().lower()
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    if arg == "today":
        return today.isoformat()
    if arg == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    # raw ISO
    try:
        return date.fromisoformat(arg).isoformat()
    except ValueError as exc:
        raise SystemExit(f"daily-digest: invalid --date {arg!r} — expected ISO YYYY-MM-DD, 'today', or 'yesterday' ({exc})")


def _inject_captures_section(text: str, section: str) -> str:
    """Replace an existing `## Captures` section with `section`, else append it.
    Idempotent — re-running the digest re-attaches without stacking duplicates."""
    block = section.rstrip() + "\n"
    if _CAPTURES_SECTION_RE.search(text):
        return _CAPTURES_SECTION_RE.sub("\n" + block, text, count=1).rstrip() + "\n"
    return text.rstrip() + "\n\n" + block


def _attach_captures_section(date_iso: str) -> None:
    """After the agent writes `daily/<date>.md`, inject the deterministic Captures
    section (capture-id → resolved interpretation + status). Best-effort: a failure
    here must never fail the digest run, and there's nothing to attach on no-capture
    days. The section is built Python-side (table lookup), not by the agent."""
    try:
        from core import capture_index

        section = capture_index.build_captures_section(date_iso)
        if not section:
            return
        digest_path = DAILY_DIR / f"{date_iso}.md"
        if not digest_path.is_file():
            return
        text = digest_path.read_text(encoding="utf-8")
        new_text = _inject_captures_section(text, section)
        if new_text != text:
            digest_path.write_text(new_text, encoding="utf-8")
            log.info("daily-digest: attached Captures section to %s", digest_path.name)
    except Exception:  # noqa: BLE001
        log.exception("daily-digest: failed to attach Captures section for %s", date_iso)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the daily-digest agent for a given date.")
    ap.add_argument("--date", default="yesterday",
                    help="ISO date YYYY-MM-DD, or 'today' / 'yesterday'. Default: yesterday.")
    args = ap.parse_args()

    target_date = _resolve_date(args.date)
    date_dir = DAILY_DIR / target_date

    if not date_dir.is_dir():
        log.info("daily-digest: no captures at %s — skipping (no-op)", date_dir.relative_to(DAILY_DIR.parent))
        return 0

    captures = sorted(p.name for p in date_dir.glob("*.md"))
    if not captures:
        log.info("daily-digest: %s/ exists but is empty — skipping", target_date)
        return 0

    log.info("daily-digest: distilling %d capture(s) for %s (%s)",
             len(captures), target_date, ", ".join(captures))

    wiki_bin = WIKI_DIR / "wiki"
    if not wiki_bin.is_file():
        log.error("daily-digest: wiki CLI not found at %s", wiki_bin)
        return 2

    cmd = [str(wiki_bin), "agent", "daily-digest", "--var", f"date={target_date}"]
    log.info("daily-digest: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=WIKI_DIR.parent)
    if result.returncode == 0:
        # The agent produced the digest; attach the deterministic Captures section.
        _attach_captures_section(target_date)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
