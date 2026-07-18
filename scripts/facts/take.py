"""Manage third-party belief attribution — WHO believes WHAT, with confidence + source.

Takes live in `knowledge/takes/<holder-slug>.md`, one file per holder, append-only
one-per-line. Each line:

    - **YYYY-MM-DD** [confidence] · `source-path` — belief prose.

Confidence ∈ {low, medium, high}. Source is a vault-relative path or a
free-form citation. Spec: `.ytstack/backlog/takes-substrate.md` (M011).

Owner-asymmetry: the operator's OWN positions live in `knowledge/facts/`
(authoritative, override compile). Takes record OTHER people's positions
(informative, do not override). Compile reads takes for `type: person`
distills only.

Usage:
    uv run python scripts/facts/take.py add "Jane Doe" \\
        "GPT-5 commoditizes agent platforms within 12 months." \\
        --confidence high \\
        --source "raw/transcripts/jamie/2026-04-15--review--abc.md"

    uv run python scripts/facts/take.py list
    uv run python scripts/facts/take.py show <holder-slug>
    uv run python scripts/facts/take.py remove <holder-slug> --line N
    uv run python scripts/facts/take.py path <holder-slug>
"""

import os
os.environ.setdefault("CLAUDE_INVOKED_BY", "take")

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import frontmatter
from core.paths import TAKES_DIR
from core.utils import slugify, today_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("take")

VALID_CONFIDENCE = ("low", "medium", "high")
DEFAULT_CONFIDENCE = "medium"

# Single source of truth for the per-line shape. Parser + writer both reference
# this — keep them symmetric. Format:
#   - **YYYY-MM-DD** [confidence] · `source` — belief prose.
TAKE_LINE_RE = re.compile(
    r"^- \*\*(?P<date>\d{4}-\d{2}-\d{2})\*\* "
    r"\[(?P<confidence>low|medium|high)\] · "
    r"`(?P<source>[^`]+)` — (?P<belief>.+)$"
)


def _take_path(slug: str) -> Path:
    return TAKES_DIR / f"{slug}.md"


# Read/write via the single core.frontmatter grammar (C03). `serialize`
# normalizes the fence/body separator, which also fixes the old writer's
# grow-one-blank-line-per-append round-trip.

def _backup(path: Path) -> Path | None:
    return frontmatter.backup(path)


def _read_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). Body excludes the YAML block."""
    return frontmatter.parse(path.read_text(encoding="utf-8"))


def _write_file(path: Path, fm: dict, body: str) -> None:
    frontmatter.write(path, fm, body)


def _initial_body(holder_display: str) -> str:
    """First-touch body skeleton (header + intro line)."""
    return f"# Takes — {holder_display}\n\n"


def _format_take_line(date: str, confidence: str, source: str, belief: str) -> str:
    """Render a single take line. Belief gets a trailing period if missing."""
    belief = belief.strip()
    if belief and not belief.endswith((".", "!", "?")):
        belief = belief + "."
    return f"- **{date}** [{confidence}] · `{source}` — {belief}"


def _parse_take_lines(body: str) -> list[dict]:
    """Return parsed takes (date/confidence/source/belief/raw) for the body."""
    out: list[dict] = []
    for raw in body.splitlines():
        m = TAKE_LINE_RE.match(raw)
        if not m:
            continue
        out.append({**m.groupdict(), "raw": raw})
    return out


def _append_take(
    holder: str,
    belief: str,
    confidence: str,
    source: str,
    *,
    date: str | None = None,
    holder_slug: str | None = None,
) -> tuple[Path, str]:
    """Append a take to `knowledge/takes/<slug>.md`, creating it if needed.

    Returns (file_path, status) where status ∈ {"appended", "duplicate"}.
    Refuses to append an exact-match line (same date + confidence + source +
    belief) — idempotent per spec.
    """
    slug = holder_slug or slugify(holder)
    if not slug:
        raise ValueError(f"could not derive a slug from holder {holder!r}")

    confidence = confidence.lower().strip()
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(
            f"confidence must be one of {list(VALID_CONFIDENCE)}, got {confidence!r}"
        )

    date = date or today_iso()
    line = _format_take_line(date, confidence, source.strip(), belief)
    path = _take_path(slug)
    today = today_iso()

    if path.exists():
        fm, body = _read_frontmatter(path)
        if not fm:
            # Existing file without parseable frontmatter — back it up and
            # rewrite with the canonical shape, preserving body content.
            _backup(path)
            fm = {
                "title": f"Takes — {holder}",
                "type": "takes",
                "holder": slug,
                "created": today,
                "last_updated": today,
            }
            if not body.strip():
                body = _initial_body(holder)
        # Idempotent: refuse an exact duplicate line.
        existing_lines = body.splitlines()
        if line in existing_lines:
            return path, "duplicate"
        body = body.rstrip() + "\n" + line + "\n"
        fm["last_updated"] = today
        # Preserve display title; if missing inject one.
        fm.setdefault("title", f"Takes — {holder}")
        fm.setdefault("type", "takes")
        fm.setdefault("holder", slug)
        fm.setdefault("created", today)
    else:
        fm = {
            "title": f"Takes — {holder}",
            "type": "takes",
            "holder": slug,
            "created": today,
            "last_updated": today,
        }
        body = _initial_body(holder) + line + "\n"

    _write_file(path, fm, body)
    return path, "appended"


# ── CLI commands ──────────────────────────────────────────────────────


def cmd_add(args: argparse.Namespace) -> int:
    holder = args.holder.strip()
    if not holder:
        log.error("holder must not be empty")
        return 2
    belief = args.belief.strip()
    if not belief:
        log.error("belief must not be empty")
        return 2
    source = args.source.strip() if args.source else ""
    if not source:
        log.error("--source is required (vault-relative path or citation sentinel)")
        return 2
    try:
        path, status = _append_take(
            holder=holder,
            belief=belief,
            confidence=args.confidence,
            source=source,
            date=args.date,
            holder_slug=args.slug,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    if status == "duplicate":
        log.info("take already recorded (no-op): %s", path)
        return 0
    print(str(path))
    return 0


def _list_take_files() -> list[Path]:
    if not TAKES_DIR.exists():
        return []
    return sorted(TAKES_DIR.glob("*.md"))


def cmd_list(args: argparse.Namespace) -> int:
    files = _list_take_files()
    if not files:
        print("(no takes recorded yet)")
        return 0
    for path in files:
        fm, body = _read_frontmatter(path)
        takes = _parse_take_lines(body)
        slug = path.stem
        title = fm.get("title", f"Takes — {slug}")
        last = fm.get("last_updated", "?")
        print(f"{slug:30s} {len(takes):>3d} take(s)  updated:{last}  {title}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _take_path(slug)
    if not path.exists():
        log.error("no takes for holder %r (looked for %s)", slug, path)
        return 1
    fm, body = _read_frontmatter(path)
    takes = _parse_take_lines(body)
    title = fm.get("title", f"Takes — {slug}")
    print(f"# {title} ({len(takes)} take(s))\n")
    if not takes:
        print("(no take lines parsed — file may be empty or malformed)")
        return 0
    for i, t in enumerate(takes, start=1):
        print(f"{i:>3d}. {t['raw']}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _take_path(slug)
    if not path.exists():
        log.error("no takes for holder %r", slug)
        return 1
    fm, body = _read_frontmatter(path)
    if args.all:
        bak = _backup(path)
        path.unlink()
        log.info("removed entire takes file %s (backup at %s)", path, bak)
        return 0
    if args.line is None:
        log.error(
            "remove requires --line N (1-based) or --all. Use `show` to list lines."
        )
        return 2
    takes = _parse_take_lines(body)
    if args.line < 1 or args.line > len(takes):
        log.error("--line %d out of range (1..%d)", args.line, len(takes))
        return 1
    target_raw = takes[args.line - 1]["raw"]
    new_body_lines = []
    removed = False
    for raw in body.splitlines():
        if not removed and raw == target_raw:
            removed = True
            continue
        new_body_lines.append(raw)
    if not removed:
        log.error("internal error: line %d not found verbatim in body", args.line)
        return 1
    _backup(path)
    new_body = "\n".join(new_body_lines) + ("\n" if new_body_lines else "")
    fm["last_updated"] = today_iso()
    _write_file(path, fm, new_body)
    log.info("removed line %d: %s", args.line, target_raw)
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _take_path(slug)
    if not path.exists():
        log.error("no takes for holder %r", slug)
        return 1
    print(str(path))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="append a new take for a holder")
    p_add.add_argument("holder", help='holder name, e.g. "Jane Doe" — slugified for the filename')
    p_add.add_argument("belief", help="one-line belief prose")
    p_add.add_argument(
        "--confidence",
        default=DEFAULT_CONFIDENCE,
        choices=list(VALID_CONFIDENCE),
        help=f"confidence tier (default {DEFAULT_CONFIDENCE}).",
    )
    p_add.add_argument(
        "--source",
        required=True,
        help="REQUIRED — vault-relative path or free-form citation "
        "(e.g. raw/transcripts/jamie/2026-04-15--abc.md, daily/2026-04-15.md, user:2026-05-13).",
    )
    p_add.add_argument(
        "--date",
        default=None,
        help="ISO date of the take (default: today).",
    )
    p_add.add_argument(
        "--slug",
        default=None,
        help="override the auto-derived slug.",
    )
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list all takes files")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show all takes for one holder")
    p_show.add_argument("slug", help="holder slug (filename without .md)")
    p_show.set_defaults(func=cmd_show)

    p_remove = sub.add_parser("remove", help="remove a take line (or the whole file)")
    p_remove.add_argument("slug", help="holder slug")
    p_remove.add_argument("--line", type=int, default=None, help="1-based line number from `show`")
    p_remove.add_argument("--all", action="store_true", help="delete the entire file (backup kept)")
    p_remove.set_defaults(func=cmd_remove)

    p_path = sub.add_parser("path", help="print absolute path of a holder's takes file")
    p_path.add_argument("slug", help="holder slug")
    p_path.set_defaults(func=cmd_path)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
