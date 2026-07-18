"""Backfill per_item frontmatter into pre-2026-05-17T16-14 reports.

Runs before the runner.py per_item-in-frontmatter commit (8f8fde4)
don't have the per_item dict, so render_summary's per-instrument
radar falls back to a placeholder SVG. This script walks every
per-instrument report under a study's runs/, parses the body's
'## Items' table for raw agent answers, applies reverse-coding
from items.yaml, and writes the resulting per_item dict into the
report's frontmatter.

Idempotent + non-destructive:
- Skips reports that already have per_item in frontmatter.
- Creates a `.bak` next to each file before rewriting.
- Marks backfilled reports with `per_item_backfilled: true` so a
  future audit can distinguish backfilled-from-body vs runner-written.

Usage:
    uv run python scripts/reports/_engine/backfill_per_item.py \\
        --study-dir ~/path/to/<vault>/reports/studies/<id>
    uv run python scripts/reports/_engine/backfill_per_item.py \\
        --study-dir ... --rerender-summary
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.core import frontmatter  # noqa: E402
from scripts.reports._engine.instrument import load_instrument  # noqa: E402
from scripts.reports._engine.lib.render_summary import render_summary  # noqa: E402
from scripts.reports._engine.lib.timeline import load_timeline  # noqa: E402


log = logging.getLogger("backfill")


# Parse a `| <id> | <answer> | ...` table row. Answer is integer or "—".
_TABLE_ROW = re.compile(
    r"^\|\s*(?P<id>\S+)\s*\|\s*(?P<ans>[—\-\d]+)\s*\|", re.MULTILINE
)


def _parse_items_table(body: str) -> dict[str, int | None]:
    """Pull {item_id: raw_answer} out of the '## Items' table in the body."""
    # Locate the table region between '## Items' and the next header.
    items_match = re.search(r"^##\s+Items\s*$", body, re.MULTILINE)
    if not items_match:
        return {}
    table_start = items_match.end()
    next_h2 = re.search(r"^##\s+\S", body[table_start:], re.MULTILINE)
    table_end = table_start + (next_h2.start() if next_h2 else len(body))
    table_region = body[table_start:table_end]

    out: dict[str, int | None] = {}
    for m in _TABLE_ROW.finditer(table_region):
        item_id = m.group("id")
        ans = m.group("ans")
        if item_id.lower() == "id":
            continue  # header row
        if set(item_id) == {"-"}:
            continue  # divider row
        if ans == "—":
            out[item_id] = None
        else:
            try:
                out[item_id] = int(ans)
            except ValueError:
                continue
    return out


def _instruments_root() -> Path:
    return Path(__file__).resolve().parent / "instruments"


def _resolve_instrument_dir(slug: str, version: str) -> Path | None:
    """Find the instrument directory in the engine repo."""
    d = _instruments_root() / slug / f"v{version}"
    return d if d.is_dir() else None


def _normalise_answers(
    raw_answers: dict[str, int | None],
    instrument_dir: Path,
) -> dict[str, int]:
    """Apply reverse-coding to raw agent answers to produce the
    normalised per-item dict used by render_summary."""
    try:
        instr = load_instrument(instrument_dir)
    except (FileNotFoundError, ValueError) as exc:
        log.warning("  could not load instrument at %s: %s", instrument_dir, exc)
        return {}

    out: dict[str, int] = {}
    for item in instr.items:
        raw = raw_answers.get(item.id)
        if raw is None:
            continue
        if item.reverse_coded:
            out[item.id] = item.scale.reverse(raw)
        else:
            out[item.id] = raw
    return out


def backfill_report(report_path: Path) -> bool:
    """Backfill one per-instrument report. Returns True if rewritten."""
    text = report_path.read_text(encoding="utf-8")
    fm, body = frontmatter.parse(text)
    if not fm:
        log.warning("  %s: no parseable frontmatter — skip", report_path.name)
        return False
    if "per_item" in fm and isinstance(fm["per_item"], dict) and fm["per_item"]:
        log.info("  %s: per_item already present (skip)", report_path.name)
        return False
    slug = str(fm.get("instrument", report_path.stem))
    version = str(fm.get("version", ""))
    instrument_dir = _resolve_instrument_dir(slug, version)
    if instrument_dir is None:
        log.warning(
            "  %s: instrument %s v%s not found in engine — skip",
            report_path.name, slug, version,
        )
        return False
    raw_answers = _parse_items_table(body)
    if not raw_answers:
        log.warning("  %s: items table empty/unparseable — skip", report_path.name)
        return False
    per_item = _normalise_answers(raw_answers, instrument_dir)
    if not per_item:
        log.info(
            "  %s: all items null (per_item would be empty) — skip",
            report_path.name,
        )
        return False

    # Backup
    bak_path = report_path.with_suffix(report_path.suffix + ".bak-backfill")
    bak_path.write_text(text, encoding="utf-8")

    # Inject per_item + per_item_backfilled into frontmatter. Write-anew via
    # core.frontmatter (these are engine-written reports, not operator YAML).
    fm["per_item"] = per_item
    fm["per_item_backfilled"] = True

    frontmatter.write(report_path, fm, body)
    log.info(
        "  %s: backfilled %d item(s); %s",
        report_path.name,
        len(per_item),
        f"backup at {bak_path.name}",
    )
    return True


def backfill_study(
    study_dir: Path, rerender_summary: bool = False
) -> tuple[int, int]:
    """Backfill all per-instrument reports under a study; optionally re-render
    meta-report for each run after backfilling. Returns (n_rewritten,
    n_runs_rerendered)."""
    runs_dir = study_dir / "runs"
    if not runs_dir.is_dir():
        log.error("no runs/ dir at %s", runs_dir)
        return (0, 0)
    rewritten = 0
    runs_rendered = 0
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        if run_dir.name.startswith("."):
            continue  # skip tmp dirs
        log.info("run %s:", run_dir.name)
        instruments_dir = run_dir / "instruments"
        if not instruments_dir.is_dir():
            continue
        run_rewrites = 0
        for report in sorted(instruments_dir.glob("*.md")):
            if backfill_report(report):
                rewritten += 1
                run_rewrites += 1
        if rerender_summary and run_rewrites > 0:
            try:
                # Trim timeline to runs up to (and including) THIS one.
                # render_summary uses timeline.latest for per-instrument
                # radar — without trimming, an older run's _summary would
                # render the NEWEST run's data, not its own. Live runs
                # don't hit this because the runner constructs the
                # timeline incrementally; backfill loops over historic
                # runs so must subset explicitly.
                from scripts.reports._engine.lib.timeline import Timeline
                full_timeline = load_timeline(study_dir)
                trimmed_runs = [
                    r for r in full_timeline.runs
                    if r.timestamp <= run_dir.name
                ]
                trimmed = Timeline(
                    study_id=full_timeline.study_id,
                    runs=trimmed_runs,
                )
                render_summary(
                    study_id=study_dir.name,
                    timeline=trimmed,
                    summary_path=run_dir / "_summary.md",
                    charts_dir=run_dir / "charts",
                )
                log.info("  → re-rendered _summary.md + charts/ (timeline trimmed to ≤ this run)")
                runs_rendered += 1
            except Exception as exc:
                log.warning("  re-render failed: %s", exc)
    return (rewritten, runs_rendered)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--study-dir", type=Path, required=True,
        help="Path to <vault>/reports/studies/<id>/",
    )
    parser.add_argument(
        "--rerender-summary", action="store_true",
        help="Also re-render _summary.md + charts/ for each touched run.",
    )
    args = parser.parse_args()
    study_dir = args.study_dir.expanduser().resolve()
    if not study_dir.is_dir():
        print(f"ERROR: study-dir not a directory: {study_dir}", file=sys.stderr)
        return 1
    n_rewritten, n_rendered = backfill_study(study_dir, args.rerender_summary)
    print(
        f"\n✓ backfill done: {n_rewritten} report(s) rewritten, "
        f"{n_rendered} meta-report(s) re-rendered."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
