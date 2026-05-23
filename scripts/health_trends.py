"""Deterministic health-trend synthesis (MVP, no LLM).

Turns the health metric corpus (`raw/notes/health/**`) into a readable trends
layer — the synthesis consumer the per-day stubs never had (per
`concepts/health-rollup-intake-format.md`: a single day is not knowledge, "(b)
future trend aggregation across many days" is). Walks the YAML frontmatter,
groups numeric metrics by month, computes coverage-aware stats (range, all-time
mean, recent-window mean, trend arrow), and writes ONE sentinel-managed
`## Trends` block into `knowledge/concepts/health.md` (created if absent).

Pure Python — $0, idempotent, coverage-aware (no fake trends across data gaps).
The narrative/LLM layer is a deliberate later addition; this is the cheap,
always-correct foundation. See `.ytstack/backlog/health-trend-synthesis.md`.

Usage:
    wiki health-trends            # regenerate the trends block
    wiki health-trends --dry-run  # print the block, write nothing
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "health_trends"

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml

from core.paths import CONCEPTS_DIR, ROOT_DIR
from core.config import CONFIG  # noqa: E402
from core.utils import now_iso  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("health-trends")

BEGIN = "<!-- health-trends:begin -->"
END = "<!-- health-trends:end -->"
HEALTH_PAGE = CONCEPTS_DIR / "health.md"

# Frontmatter keys that are bookkeeping, not biometrics — never aggregate.
# (Everything else is aggregated only if its value parses as a real number.)
_SKIP_KEYS = {"date"}


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def collect_metrics(health_dir: Path) -> tuple[dict[str, list[tuple[str, float]]], int, tuple[str, str]]:
    """Return (metric -> [(date, value)] sorted by date, day_count, (min_date, max_date)).

    A metric value counts only if it parses as a real number (int/float). `date`
    and any non-numeric field (sensitivity, sources, title, …) are ignored.
    """
    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    dates: list[str] = []
    for f in sorted(health_dir.rglob("*.md")):
        fm = _parse_frontmatter(f.read_text(encoding="utf-8"))
        date = fm.get("date")
        if not isinstance(date, str):
            continue
        dates.append(date)
        for k, v in fm.items():
            if k in _SKIP_KEYS or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                series[k].append((date, float(v)))
    for k in series:
        series[k].sort(key=lambda dv: dv[0])
    span = (min(dates), max(dates)) if dates else ("", "")
    return series, len(dates), span


def _months_back(anchor: str, count: int, skip: int = 0) -> set[str]:
    """The `count` calendar months (`YYYY-MM`) ending `skip` months before `anchor`.

    skip=0 → the `count` months up to and including anchor's month (the recent
    window). skip=count → the `count` months immediately before that (the prior
    window). Calendar-based, not data-based: a month with no data is still part
    of the window, so a metric that stopped logging shows up as empty/recent='—'.
    """
    y, m = int(anchor[:4]), int(anchor[5:7])
    out: set[str] = set()
    for i in range(skip, skip + count):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        out.add(f"{yy:04d}-{mm:02d}")
    return out


def _trend_arrow(values_by_date: list[tuple[str, float]], recent_months: int, anchor: str) -> str:
    """Compare the recent calendar window's mean against the equal-length prior one.

    Both windows are anchored at `anchor` (the corpus max month) so EVERY metric
    is judged on the same wall-clock window. A metric with <3 points in the recent
    window yields '·' (no recent signal) — never a stale 'trend' built from data
    that happens to be the metric's most recent logging but is years old.
    """
    if not anchor:
        return "·"
    recent_set = _months_back(anchor, recent_months)
    prior_set = _months_back(anchor, recent_months, recent_months)
    recent = [v for d, v in values_by_date if d[:7] in recent_set]
    prior = [v for d, v in values_by_date if d[:7] in prior_set]
    if len(recent) < 3 or len(prior) < 3:
        return "·"
    r, p = mean(recent), mean(prior)
    if p == 0:
        return "→"
    delta = (r - p) / abs(p)
    if delta > 0.05:
        return "↑"
    if delta < -0.05:
        return "↓"
    return "→"


def _fmt(x: float) -> str:
    return f"{x:.0f}" if abs(x) >= 100 or x == int(x) else f"{x:.1f}"


def render_block(health_dir: Path) -> str:
    series, days, (lo, hi) = collect_metrics(health_dir)
    recent_months = CONFIG.limits.health_trends_recent_months
    min_days = CONFIG.limits.health_trends_min_coverage_days
    anchor = hi[:7] if hi else ""  # corpus-wide recent-window reference (max data month)

    rows = []
    for metric in sorted(series, key=lambda m: -len(series[m])):
        vals = series[metric]
        if len(vals) < min_days:
            continue
        nums = [v for _, v in vals]
        recent_set = _months_back(anchor, recent_months) if anchor else set()
        recent_nums = [v for d, v in vals if d[:7] in recent_set]
        recent_avg = _fmt(mean(recent_nums)) if recent_nums else "—"
        rows.append(
            f"| `{metric}` | {len(vals)} | {_fmt(min(nums))}–{_fmt(max(nums))} "
            f"| {_fmt(mean(nums))} | {recent_avg} | {_trend_arrow(vals, recent_months, anchor)} |"
        )

    body = [
        BEGIN,
        "",
        "## Trends",
        "",
        f"_{days} days · {lo} → {hi} · deterministic monthly aggregation, "
        f"regenerated by `wiki health-trends` ({now_iso()[:10]}). Trend = last "
        f"{recent_months}mo vs prior {recent_months}mo (±5%)._",
        "",
        "| Metric | Days | Range | All-time avg | "
        f"Last {recent_months}mo | Trend |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        END,
    ]
    return "\n".join(body)


def _upsert_block(page: Path, block: str) -> str:
    """Insert/replace the health-trends sentinel block in `page` (create if absent).

    Mirrors the backlinks-footer sentinel pattern. Placed before the
    `<!-- backlinks:begin -->` footer if present, else appended.
    """
    if not page.exists():
        page.parent.mkdir(parents=True, exist_ok=True)
        return (
            "---\ntitle: Health\ntype: concept\n"
            "tags: [personal, biometrics]\n---\n\n# Health\n\n"
            "Operator's personal health metrics — trends auto-aggregated below.\n\n"
            + block + "\n"
        )
    text = page.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        b = text.find(BEGIN)
        e = text.find(END) + len(END)
        return text[:b] + block + text[e:]
    if "<!-- backlinks:begin -->" in text:
        i = text.find("<!-- backlinks:begin -->")
        return text[:i] + block + "\n\n" + text[i:]
    return text.rstrip() + "\n\n" + block + "\n"


def run(dry_run: bool) -> int:
    health_dir = ROOT_DIR / "raw" / "notes" / "health"
    if not health_dir.exists():
        log.info("No raw/notes/health/ — nothing to aggregate.")
        return 0
    block = render_block(health_dir)
    if dry_run:
        print(block)
        return 0
    new_text = _upsert_block(HEALTH_PAGE, block)
    HEALTH_PAGE.write_text(new_text, encoding="utf-8")
    log.info("Wrote health-trends block to %s", HEALTH_PAGE.relative_to(ROOT_DIR))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic health-trend synthesis.")
    parser.add_argument("--dry-run", action="store_true", help="print the block, write nothing")
    args = parser.parse_args()
    if not CONFIG.features.health_trends and not args.dry_run:
        log.warning(
            "features.health_trends is OFF — printing dry-run instead. "
            "Flip the flag in config.yaml to write the block."
        )
        return run(dry_run=True)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
