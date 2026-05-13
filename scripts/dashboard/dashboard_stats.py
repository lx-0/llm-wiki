"""Generate `_dashboard-stats.md` at vault root with current pipeline counts.

Reads `state.json` + filesystem + cheap structural lint checks; writes a
Markdown fragment that `dashboard.md` transcludes via `![[_dashboard-stats]]`.

Runs after every flush (called from `flush.py` post-compile). Also runnable
standalone:

    uv run python scripts/dashboard/dashboard_stats.py            # write
    uv run python scripts/dashboard/dashboard_stats.py --dry-run  # print without writing
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["CLAUDE_INVOKED_BY"] = "dashboard_stats"

import argparse
import json
import logging
from datetime import datetime, timezone

from core.config import (
    DAILY_DIR,
    KNOWLEDGE_DIR,
    ROOT_DIR,
    SESSIONS_DIR,
    now_iso,
)
from core.utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dashboard-stats")

OUTPUT_FILE = ROOT_DIR / "_dashboard-stats.md"
FAILED_DIR = SESSIONS_DIR / "failed-flushes"


# ── Counters ────────────────────────────────────────────────────────


def list_pending_compiles() -> list[str]:
    """Return relative paths of raw/daily files whose hash differs from `state.ingested`.
    Caller decides whether to count or display."""
    state = load_state()
    ingested = state.get("ingested", {})
    pending: list[str] = []
    for f in list_raw_files():
        rel = str(f.relative_to(ROOT_DIR))
        try:
            current_hash = file_hash(f)
        except (OSError, ValueError):
            continue
        if ingested.get(rel) != current_hash:
            pending.append(rel)
    pending.sort()
    return pending


def count_pending_compiles() -> int:
    return len(list_pending_compiles())


def count_failed_flushes() -> int:
    if not FAILED_DIR.exists():
        return 0
    return sum(1 for p in FAILED_DIR.iterdir() if p.is_file() and p.suffix == ".md")


def count_lint_warnings() -> int:
    """Sum issues across the cheap (non-LLM) lint checks."""
    from lint import (
        check_article_type,
        check_broken_links,
        check_missing_backlinks,
        check_orphan_pages,
        check_orphan_sources,
        check_stale_articles,
    )

    total = 0
    checks = (
        check_broken_links,
        check_orphan_pages,
        check_orphan_sources,
        check_stale_articles,
        check_missing_backlinks,
        check_article_type,
    )
    for fn in checks:
        try:
            issues = fn()
            total += len(issues)
        except Exception as exc:  # noqa: BLE001 — defensive: lint must not crash dashboard
            log.warning("lint check %s failed: %s", fn.__name__, exc)
    return total


def total_cost_lifetime() -> float:
    state = load_state()
    return float(state.get("total_cost", 0.0))


def latest_compile_ts() -> str | None:
    """Mtime (ISO) of the newest article in `knowledge/`, or None if empty."""
    articles = list_wiki_articles()
    if not articles:
        return None
    newest = max(articles, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc).isoformat()


def compute_stats() -> dict:
    pending = list_pending_compiles()
    return {
        "pending_compiles": len(pending),
        "pending_compile_paths": pending,
        "failed_flushes": count_failed_flushes(),
        "lint_warnings": count_lint_warnings(),
        "total_cost_lifetime": round(total_cost_lifetime(), 4),
        "articles_total": len(list_wiki_articles()),
        "daily_logs_total": len(list(DAILY_DIR.glob("*.md"))) if DAILY_DIR.exists() else 0,
        "last_compile_ts": latest_compile_ts(),
        "generated_at": now_iso(),
    }


# ── Render ──────────────────────────────────────────────────────────


def render_callout(stats: dict) -> str:
    pending = stats["pending_compiles"]
    failed = stats["failed_flushes"]
    lint = stats["lint_warnings"]
    cost = stats["total_cost_lifetime"]
    articles = stats["articles_total"]
    daily = stats["daily_logs_total"]
    last = stats["last_compile_ts"] or "never"

    pending_icon = "🟢" if pending == 0 else ("🟡" if pending < 10 else "🔴")
    failed_icon = "🟢" if failed == 0 else "🔴"
    lint_icon = "🟢" if lint == 0 else ("🟡" if lint < 10 else "🔴")

    callout = (
        "> [!info] Pipeline status\n"
        f"> {pending_icon} **Pending compiles:** {pending}\n"
        f"> {failed_icon} **Failed flushes:** {failed}\n"
        f"> {lint_icon} **Lint warnings:** {lint}\n"
        f"> 💰 **LLM spend (lifetime):** ${cost:.2f}\n"
        f"> 📚 **Articles:** {articles} · **Daily logs:** {daily}\n"
        f"> 🕐 **Last compile:** {last}\n"
    )

    pending_paths = stats.get("pending_compile_paths", [])
    if pending_paths:
        preview_n = 20
        shown = pending_paths[:preview_n]
        more = len(pending_paths) - len(shown)
        items = "\n".join(f"- [[{p}]]" for p in shown)
        if more > 0:
            items += f"\n- _… and {more} more_"
        callout += (
            "\n## ⏭ Pending compile\n\n"
            f"{items}\n"
        )

    return callout


def write_dashboard_stats(stats: dict, callout: str) -> Path:
    """Write `_dashboard-stats.md` with frontmatter + callout body."""
    fm_keys = (
        "pending_compiles",
        "failed_flushes",
        "lint_warnings",
        "total_cost_lifetime",
        "articles_total",
        "daily_logs_total",
    )
    lines = ["---"]
    for key in fm_keys:
        lines.append(f"{key}: {stats[key]}")
    last_ts = stats["last_compile_ts"]
    lines.append(f"last_compile_ts: {last_ts if last_ts is not None else 'null'}")
    lines.append(f"generated_at: {stats['generated_at']}")
    lines.append("---")
    lines.append("")
    lines.append(callout)
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    return OUTPUT_FILE


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print stats without writing")
    args = parser.parse_args()

    stats = compute_stats()
    callout = render_callout(stats)

    if args.dry_run:
        print(json.dumps(stats, indent=2))
        print()
        print(callout)
        return 0

    out = write_dashboard_stats(stats, callout)
    log.info(
        "Wrote %s — pending=%d failed=%d lint=%d cost=$%.2f articles=%d",
        out,
        stats["pending_compiles"],
        stats["failed_flushes"],
        stats["lint_warnings"],
        stats["total_cost_lifetime"],
        stats["articles_total"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
