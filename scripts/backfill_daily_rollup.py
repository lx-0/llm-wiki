"""One-shot backfill: existing substrate files → daily/<date>/<source>.md.

The Phase 2 wiring only fires when collectors run *after* the wiring landed.
Substrate files that existed *before* (90 days of Oura backfill in
`raw/notes/health/`, all the jamie / gmeet transcripts, voice intakes, etc.)
have no entries in the daily/-rollup yet.

This script walks each substrate folder, extracts the natural per-row
metadata, and appends a one-liner to `daily/<date>/<source>.md` for each
historical file. Idempotent — re-running skips lines that already exist.

Usage:

    uv run python scripts/backfill_daily_rollup.py --vault <path> [--source SRC] [--dry-run]

`--source` defaults to `all` (health, voice, meetings). Pick one to scope
the backfill while debugging.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import re
import sys
from pathlib import Path

from core import frontmatter
from core.console import setup_console_logging
from core.utils import ellipsize

log = logging.getLogger("backfill_daily_rollup")


# ── Filename / frontmatter extractors per substrate ──────────────────


_HEALTH_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})--(?P<account>[a-z0-9-]+)\.md$")
# jamie + gmeet share the shape `<date>--<slug>--<short>.md`. The `<short>`
# fragment is alphanumeric (hex for some Jamie ids, mixed-case base62 for
# Drive Doc ids on gmeet), so accept any [A-Za-z0-9_-] run. Use a non-greedy
# slug so the rightmost `--` separates short-id correctly even when the slug
# itself contains hyphens.
_JAMIE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})--(?P<slug>.+)--(?P<short>[A-Za-z0-9_-]+)\.md$")
_GMEET_NAME_RE = _JAMIE_NAME_RE
_VOICE_NAME_RE = re.compile(r"^voice-(\d{4}-\d{2}-\d{2})-(?P<time>\d{4})-(?P<slug>[a-z0-9-]+)\.md$")


def _read_frontmatter(path: Path) -> dict:
    """Frontmatter via the single `core.frontmatter` grammar (C03). No fence → `{}`
    silently; a malformed block logs the file path and yields `{}` — a backfill must
    say which file it skipped (tests/test_errors.py pins the message)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if frontmatter.split_fence(text)[0] is None:
        return {}
    try:
        return frontmatter.parse_strict(text)[0]
    except frontmatter.FrontmatterError as e:
        log.warning("frontmatter parse failed for %s: %s", path, e)
        return {}


# ── Per-substrate rollup-line generators ─────────────────────────────


def _health_lines(vault: Path) -> list[tuple[str, str]]:
    """Walk raw/notes/health/<year>/<date>--<account>.md, yield (date, line)."""
    root = vault / "raw" / "notes" / "health"
    if not root.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for f in sorted(root.glob("*/*.md")):
        m = _HEALTH_NAME_RE.match(f.name)
        if not m:
            continue
        date_iso, account = m.group(1), m.group("account")
        fm = _read_frontmatter(f)
        bits: list[str] = []
        if fm.get("sleep_hours") is not None:
            bits.append(f"sleep {float(fm['sleep_hours']):.1f}h")
        if fm.get("sleep_score") is not None:
            bits.append(f"score {fm['sleep_score']}")
        if fm.get("readiness_score") is not None:
            bits.append(f"readiness {fm['readiness_score']}")
        if fm.get("hrv_overnight") is not None:
            bits.append(f"hrv {fm['hrv_overnight']}")
        if fm.get("steps") is not None:
            bits.append(f"{fm['steps']} steps")
        if fm.get("resting_hr") is not None:
            bits.append(f"resting {fm['resting_hr']}")
        if not bits:
            continue
        line = f"- **{account}** · {' · '.join(bits)}"
        out.append((date_iso, line))
    return out


def _voice_lines(vault: Path) -> list[tuple[str, str]]:
    """Walk raw/voice/voice-<date>-<HHMM>-<slug>.md, yield (date, line)."""
    root = vault / "raw" / "voice"
    if not root.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for f in sorted(root.glob("voice-*.md")):
        m = _VOICE_NAME_RE.match(f.name)
        if not m:
            continue
        date_iso, time4 = m.group(1), m.group("time")
        time_label = f"{time4[:2]}:{time4[2:]}"
        # Body first line for the rollup
        try:
            body = f.read_text(encoding="utf-8")
        except OSError:
            continue
        body_no_fm = frontmatter.split_fence(body)[1].strip()
        first_line = ellipsize(body_no_fm.splitlines()[0].strip() if body_no_fm else "(empty)")
        line = f"- **{time_label}** · {first_line} → [[{f.stem}]]"
        out.append((date_iso, line))
    return out


def _meetings_lines(vault: Path) -> list[tuple[str, str]]:
    """Walk raw/transcripts/{jamie,gmeet}/*.md, yield (date, line)."""
    out: list[tuple[str, str]] = []
    for source_name, folder in (("jamie", "jamie"), ("gmeet", "gmeet")):
        root = vault / "raw" / "transcripts" / folder
        if not root.is_dir():
            continue
        for f in sorted(root.glob("*.md")):
            m = _JAMIE_NAME_RE.match(f.name)
            if not m:
                continue
            date_iso = m.group(1)
            # Title from frontmatter `title:`, fall back to slug
            title = None
            with contextlib.suppress(OSError):
                title = frontmatter.field(f.read_text(encoding="utf-8")[:4000], "title")
            title = title or m.group("slug").replace("-", " ")
            line = f"- **{source_name}** · {title} → [[{f.stem}]]"
            out.append((date_iso, line))
    return out


# ── Idempotent appender ──────────────────────────────────────────────


def _append_if_absent(
    daily_root: Path, date_iso: str, source: str, line: str, *, dry_run: bool
) -> bool:
    """Append the line to daily/<date>/<source>.md if it's not already there.
    Returns True if a write would happen (or did happen)."""
    subfolder = daily_root / date_iso
    target = subfolder / f"{source}.md"
    existing = ""
    if target.is_file():
        existing = target.read_text(encoding="utf-8")
    if line in existing:
        return False
    if dry_run:
        return True
    subfolder.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return True


# ── Main ─────────────────────────────────────────────────────────────


_SOURCES = {
    "health": (_health_lines, "health"),
    "voice": (_voice_lines, "voice"),
    "meetings": (_meetings_lines, "meetings"),
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill daily/-rollup from existing substrate files."
    )
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--source", choices=["all", *list(_SOURCES)], default="all")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    setup_console_logging("backfill_daily_rollup")

    if not args.vault.is_dir():
        print(f"error: --vault {args.vault} is not a directory", file=sys.stderr)
        return 2

    daily_root = args.vault / "daily"
    daily_root.mkdir(parents=True, exist_ok=True)

    sources = list(_SOURCES) if args.source == "all" else [args.source]
    total_appended = 0
    total_skipped = 0
    by_source: dict[str, tuple[int, int]] = {}

    for src in sources:
        gen, target_source = _SOURCES[src]
        rows = gen(args.vault)
        appended = 0
        skipped = 0
        for date_iso, line in rows:
            if _append_if_absent(daily_root, date_iso, target_source, line, dry_run=args.dry_run):
                appended += 1
            else:
                skipped += 1
        by_source[src] = (appended, skipped)
        total_appended += appended
        total_skipped += skipped
        verb = "would append" if args.dry_run else "appended"
        log.info("  %s: %s %d line(s), skipped %d (already present)", src, verb, appended, skipped)

    log.info("")
    log.info(
        "backfill-daily-rollup totals: %s %d line(s), skipped %d (vault=%s, dry_run=%s)",
        "would append" if args.dry_run else "appended",
        total_appended,
        total_skipped,
        args.vault,
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
