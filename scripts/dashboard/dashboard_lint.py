"""Generate `_dashboard-lint.md` at vault root with current lint queues.

Queues: orphan pages, stale articles, failed flushes (`SESSIONS_DIR/
failed-flushes/*.md`). Writes a Markdown fragment that `dashboard.md`
transcludes section by section via `![[_dashboard-lint#Section]]` embeds.

Runs after every flush (called from `flush.py` right after
`dashboard_stats.py`). The structural check results are computed ONCE per
refresh (C04): the stats run persists them via `dashboard.lint_results`; this
script consumes that cache while fresh and only recomputes when run
standalone:

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

from core.config import CONFIG
from core.paths import ROOT_DIR, SESSIONS_DIR
from core.utils import now_iso
from dashboard.lint_results import LintResults, compute_lint_results, load_fresh_cache

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


def compute_lint_data(results: LintResults | None = None) -> dict:
    """Assemble the queue lists from shared lint results (computed here only
    when the caller has none — the flush path hands in the stats run's)."""
    if results is None:
        results = compute_lint_results()
    orphans = [_issue_to_entry(i) for i in results.get("orphan_pages")]
    stale = [_issue_to_entry(i) for i in results.get("stale_articles")]
    failed = collect_failed_flushes()
    return {
        "orphans_count": len(orphans),
        "stale_count": len(stale),
        "failed_flushes_count": len(failed),
        "orphans": orphans,
        "stale": stale,
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

    # Within a flush refresh, dashboard_stats.py (spawned seconds before this
    # script) already computed + cached the structural results — reuse them.
    # Standalone runs find a stale/absent cache and recompute.
    results = load_fresh_cache(max_age_s=CONFIG.limits.dashboard_refresh_timeout_s)
    if results is not None:
        log.info("Using shared lint results from %s (computed by dashboard_stats)",
                 results.generated_at)
    data = compute_lint_data(results)
    body = render_body(data)

    if args.dry_run:
        meta = {k: data[k] for k in (
            "orphans_count", "stale_count",
            "failed_flushes_count", "last_updated_ts",
        )}
        print(json.dumps(meta, indent=2))
        print()
        print(body)
        return 0

    out = write_dashboard_lint(data, body)
    log.info(
        "Wrote %s — orphans=%d stale=%d failed=%d",
        out,
        data["orphans_count"],
        data["stale_count"],
        data["failed_flushes_count"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
