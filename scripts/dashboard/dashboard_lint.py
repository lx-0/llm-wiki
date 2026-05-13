"""Generate `_dashboard-lint.md` at vault root with current lint queues.

Imports `check_orphan_pages`, `check_stale_articles`, `check_missing_backlinks`
from `lint`; enumerates `SESSIONS_DIR/failed-flushes/*.md` for the fourth queue.
Writes a Markdown fragment that `dashboard.md` transcludes section by section
via `![[_dashboard-lint#Section]]` embeds.

Runs after every flush (called from `flush.py` post-`refresh_dashboard_stats`).
Also runnable standalone:

    uv run python scripts/dashboard/dashboard_lint.py            # write
    uv run python scripts/dashboard/dashboard_lint.py --dry-run  # print without writing
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["CLAUDE_INVOKED_BY"] = "dashboard_lint"

import argparse
import json
import logging

from core.config import ROOT_DIR, SESSIONS_DIR, now_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dashboard-lint")

OUTPUT_FILE = ROOT_DIR / "_dashboard-lint.md"
FAILED_DIR = SESSIONS_DIR / "failed-flushes"

DETAIL_TRUNCATE_AT = 120

SECTIONS = (
    ("orphans", "Orphans"),
    ("stale", "Stale"),
    ("missing_backlinks", "Missing backlinks"),
    ("failed_flushes", "Failed flushes"),
)


# -- Issue -> {link, detail} normalisation --------------------------

def _issue_to_entry(issue) -> dict:
    """Normalise a lint Issue (dataclass / dict / tuple) to {link, detail}."""
    if isinstance(issue, dict):
        link = issue.get("link") or issue.get("path") or issue.get("file") or ""
        detail = issue.get("detail") or issue.get("message") or ""
    else:
        link = getattr(issue, "path", None) or getattr(issue, "file", None) or ""
        detail = getattr(issue, "detail", None) or getattr(issue, "message", "") or ""
    return {"link": str(link), "detail": str(detail)}


# -- Counters --------------------------------------------------------

def collect_orphans() -> list[dict]:
    try:
        from lint import check_orphan_pages
        return [_issue_to_entry(i) for i in check_orphan_pages()]
    except Exception as exc:
        log.warning("check_orphan_pages failed: %s", exc)
        return []


def collect_stale() -> list[dict]:
    try:
        from lint import check_stale_articles
        return [_issue_to_entry(i) for i in check_stale_articles()]
    except Exception as exc:
        log.warning("check_stale_articles failed: %s", exc)
        return []


def collect_missing_backlinks() -> list[dict]:
    try:
        from lint import check_missing_backlinks
        return [_issue_to_entry(i) for i in check_missing_backlinks()]
    except Exception as exc:
        log.warning("check_missing_backlinks failed: %s", exc)
        return []


def collect_failed_flushes() -> list[dict]:
    if not FAILED_DIR.exists():
        return []
    entries = []
    for p in sorted(FAILED_DIR.iterdir()):
        if not p.is_file() or p.suffix != ".md":
            continue
        # First non-empty line as detail (cheap heuristic).
        try:
            first_line = next(
                (line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()),
                "",
            )
        except OSError:
            first_line = ""
        rel = str(p.relative_to(ROOT_DIR)) if p.is_relative_to(ROOT_DIR) else str(p)
        entries.append({"link": rel, "detail": first_line})
    return entries


def compute_lint_data() -> dict:
    orphans = collect_orphans()
    stale = collect_stale()
    missing = collect_missing_backlinks()
    failed = collect_failed_flushes()
    return {
        "orphans_count": len(orphans),
        "stale_count": len(stale),
        "missing_backlinks_count": len(missing),
        "failed_flushes_count": len(failed),
        "orphans": orphans,
        "stale": stale,
        "missing_backlinks": missing,
        "failed_flushes": failed,
        "last_updated_ts": now_iso(),
    }


# -- Render ----------------------------------------------------------

def _truncate(detail: str) -> str:
    if len(detail) <= DETAIL_TRUNCATE_AT:
        return detail
    return detail[: DETAIL_TRUNCATE_AT - 1].rstrip() + "…"


def _render_section(title: str, entries: list[dict]) -> str:
    lines = [f"## {title}", ""]
    for e in entries:
        lines.append(f"- [[{e['link']}]] — {_truncate(e['detail'])}")
    lines.append("")
    return "\n".join(lines)


def render_body(data: dict) -> str:
    parts = []
    for key, title in SECTIONS:
        parts.append(_render_section(title, data.get(key, [])))
    return "\n".join(parts)


# -- Write -----------------------------------------------------------

def write_dashboard_lint(data: dict, body: str) -> Path:
    fm_keys = (
        "orphans_count",
        "stale_count",
        "missing_backlinks_count",
        "failed_flushes_count",
    )
    lines = ["---"]
    for k in fm_keys:
        lines.append(f"{k}: {data[k]}")
    lines.append(f"last_updated_ts: {data['last_updated_ts']}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    return OUTPUT_FILE


# -- Main ------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print without writing")
    args = parser.parse_args()

    data = compute_lint_data()
    body = render_body(data)

    if args.dry_run:
        meta = {k: data[k] for k in (
            "orphans_count", "stale_count", "missing_backlinks_count",
            "failed_flushes_count", "last_updated_ts",
        )}
        print(json.dumps(meta, indent=2))
        print()
        print(body)
        return 0

    out = write_dashboard_lint(data, body)
    log.info(
        "Wrote %s — orphans=%d stale=%d missing=%d failed=%d",
        out,
        data["orphans_count"],
        data["stale_count"],
        data["missing_backlinks_count"],
        data["failed_flushes_count"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
