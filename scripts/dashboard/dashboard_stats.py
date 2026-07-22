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
import re
from datetime import datetime, timezone

from core.paths import DAILY_DIR, KNOWLEDGE_DIR, ROOT_DIR, SESSIONS_DIR
from core.utils import (
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    now_iso,
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


def count_lint_warnings(lint_results=None) -> int:
    """Sum issues across the cheap (non-LLM) structural lint checks.

    ``lint_results`` is a `lint_results.LintResults` computed once per refresh
    (C04) — passed by `main()` so stats + the follow-up dashboard_lint run share
    ONE corpus read. None (direct call) computes fresh."""
    from dashboard.lint_results import compute_lint_results

    if lint_results is None:
        lint_results = compute_lint_results()
    return lint_results.total


def total_cost_lifetime() -> float:
    state = load_state()
    return float(state.get("total_cost", 0.0))


def total_tokens_lifetime() -> int:
    """Sum input+output tokens across the whole usage ledger (state/usage.json).

    The honest lifetime usage figure (tokens per provider/model), replacing the
    dollar `LLM spend` surface (DECISIONS 2026-05-23). 0 when the ledger is
    absent (no LLM run yet)."""
    from core.usage import USAGE_FILE
    if not USAGE_FILE.exists():
        return 0
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    total = 0
    for day in data.values():
        for u in day.values():
            total += int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0))
    return total


def latest_compile_ts() -> str | None:
    """Mtime (ISO) of the newest article in `knowledge/`, or None if empty."""
    articles = list_wiki_articles()
    if not articles:
        return None
    newest = max(articles, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc).isoformat()


def _is_final_only(article: Path) -> bool:
    """True iff the article's frontmatter has ``compile_role: final-only``.

    Files marked final-only are hand-curated archives — visible via grep + graph
    + Obsidian search, but excluded from dashboard active surfaces (and from
    MOC auto-includes + ``wiki query`` default scope). Regex-only to keep this
    hot in the stats loop. (M007-S03-T01.)
    """
    try:
        text = article.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    block = text[3:end]
    return bool(
        re.search(
            r"^compile_role:\s*[\"']?final-only[\"']?\s*$",
            block,
            re.MULTILINE,
        )
    )


def _open_action_items_in_entities(knowledge_dir: Path = KNOWLEDGE_DIR) -> tuple[int, int]:
    """Return (open_commitments_count, entities_with_action_items_count).

    Scans `knowledge/people/*.md` + `knowledge/projects/*.md`, locates each file's
    `## Action Items` section, and counts non-empty lines that begin with `- [ ]`
    (open). `- [x]`/`- [X]` (operator-checked) excluded. Used by the dashboard
    stat-card to surface the personal-task layer (M005 entity-pages).
    """
    import re
    open_total = 0
    entities_with = 0
    for folder in ("people", "projects"):
        folder_path = knowledge_dir / folder
        if not folder_path.exists():
            continue
        for article in sorted(folder_path.glob("*.md")):
            if article.name in ("index.md", "log.md"):
                continue
            if _is_final_only(article):
                continue  # archived entities don't contribute to active threads
            try:
                text = article.read_text(encoding="utf-8")
            except OSError:
                continue
            ai_match = re.search(r"^## Action Items\s*$", text, re.MULTILINE)
            if not ai_match:
                continue
            after = text[ai_match.end():]
            section_end = re.search(r"^(## |---\s*$)", after, re.MULTILINE)
            section = after[:section_end.start()] if section_end else after
            file_open = 0
            for raw_line in section.splitlines():
                line = raw_line.strip()
                if line.startswith("- [ ]"):
                    file_open += 1
            if file_open:
                open_total += file_open
                entities_with += 1
    return open_total, entities_with


def compute_stats(lint_results=None) -> dict:
    pending = list_pending_compiles()
    open_commitments, entities_with_action_items = _open_action_items_in_entities()
    # Active surfaces exclude compile_role: final-only (archived hand-curated
    # articles still reachable via grep/graph/Obsidian search, just hidden from
    # active counts). articles_final_only surfaces the count so operator sees
    # how many are archived without their content polluting active panes.
    all_articles = list_wiki_articles()
    articles_final_only = sum(1 for a in all_articles if _is_final_only(a))
    articles_active = len(all_articles) - articles_final_only
    return {
        "pending_compiles": len(pending),
        "pending_compile_paths": pending,
        "failed_flushes": count_failed_flushes(),
        "lint_warnings": count_lint_warnings(lint_results),
        "total_cost_lifetime": round(total_cost_lifetime(), 4),
        "total_tokens_lifetime": total_tokens_lifetime(),
        "articles_total": articles_active,
        "articles_final_only": articles_final_only,
        "daily_logs_total": len(list(DAILY_DIR.glob("*.md"))) if DAILY_DIR.exists() else 0,
        "open_commitments": open_commitments,
        "entities_with_action_items": entities_with_action_items,
        "last_compile_ts": latest_compile_ts(),
        "generated_at": now_iso(),
    }


# ── Render ──────────────────────────────────────────────────────────


def render_callout(stats: dict) -> str:
    pending = stats["pending_compiles"]
    failed = stats["failed_flushes"]
    lint = stats["lint_warnings"]
    tokens = stats.get("total_tokens_lifetime", 0)
    articles = stats["articles_total"]
    daily = stats["daily_logs_total"]
    last = stats["last_compile_ts"] or "never"

    pending_icon = "🟢" if pending == 0 else ("🟡" if pending < 10 else "🔴")
    failed_icon = "🟢" if failed == 0 else "🔴"
    lint_icon = "🟢" if lint == 0 else ("🟡" if lint < 10 else "🔴")

    open_commitments = stats.get("open_commitments", 0)
    entities_with = stats.get("entities_with_action_items", 0)
    if open_commitments == 0:
        commitments_line = (
            "> 📌 **Commitments inbox:** empty — "
            "first jamie/gmeet compile will populate this from meeting substrates.\n"
        )
    else:
        commitments_line = (
            f"> 📌 **Open commitments:** {open_commitments} across "
            f"{entities_with} {'entity' if entities_with == 1 else 'entities'}\n"
        )

    callout = (
        "> [!info] Pipeline status\n"
        f"> {pending_icon} **Pending compiles:** {pending}\n"
        f"> {failed_icon} **Failed flushes:** {failed}\n"
        f"> {lint_icon} **Lint warnings:** {lint}\n"
        f"> 🔢 **LLM tokens (lifetime):** {tokens:,}\n"
        f"> 📚 **Articles:** {articles} · **Daily logs:** {daily}\n"
        f"{commitments_line}"
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
        "total_tokens_lifetime",
        "articles_total",
        "daily_logs_total",
        "open_commitments",
        "entities_with_action_items",
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

    # Compute the structural lint results ONCE (C04): the count feeds the stats
    # callout here, the full lists are persisted for the dashboard_lint run that
    # flush.py spawns right after this script — one corpus read per refresh.
    from dashboard.lint_results import compute_lint_results, save_cache

    lint_results = compute_lint_results()
    stats = compute_stats(lint_results)
    callout = render_callout(stats)

    if args.dry_run:
        print(json.dumps(stats, indent=2))
        print()
        print(callout)
        return 0

    save_cache(lint_results)
    out = write_dashboard_stats(stats, callout)
    log.info(
        "Wrote %s — pending=%d failed=%d lint=%d tokens=%s articles=%d",
        out,
        stats["pending_compiles"],
        stats["failed_flushes"],
        stats["lint_warnings"],
        f"{stats.get('total_tokens_lifetime', 0):,}",
        stats["articles_total"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
