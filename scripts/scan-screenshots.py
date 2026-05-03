"""
Scan ~/Screenshots/ for new screenshots, describe them with local LLM (gemma4 vision),
and save as raw notes for wiki compilation.

Runs as a daily piggyback task. Tracks last scan timestamp in state file.

Usage:
    uv run python scripts/scan-screenshots.py                    # scan new screenshots
    uv run python scripts/scan-screenshots.py --all               # all without sidecar
    uv run python scripts/scan-screenshots.py --all --limit 50    # batch of 50
    uv run python scripts/scan-screenshots.py --backfill 7        # last 7 days
    uv run python scripts/scan-screenshots.py --dry-run            # show what would be processed
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx  # noqa: E402  exception types only; HTTP via ollama_client

import ollama_client
from config import RAW_DIR, ROOT_DIR, STATE_DIR, TIMEZONE, now_iso
from utils import load_json_state, save_json_state
from wiki_config import CONFIG

# ── Config ──────────────────────────────────────────────────────────

SCREENSHOTS_DIR = Path.home() / "Screenshots"
REPORT_DIR = RAW_DIR / "notes" / "screenshots"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "screenshot-state.json"

MODEL = CONFIG.models.vision_model
RESIZE_WIDTH = CONFIG.limits.screenshot_resize_width
_screenshot_pb = CONFIG.piggybacks.get("scan_screenshots")
MAX_PER_RUN = (_screenshot_pb.max_per_run if _screenshot_pb else None) or 50
TIMEOUT = float(CONFIG.limits.screenshot_timeout_seconds)

TZ = ZoneInfo(TIMEZONE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("scan-screenshots")

from prompts import render  # noqa: E402


# ── State ───────────────────────────────────────────────────────────

def _load_state() -> dict:
    return load_json_state(STATE_FILE)


def _save_state(state: dict) -> None:
    save_json_state(STATE_FILE, state)


# ── Screenshot Discovery ────────────────────────────────────────────

def find_new_screenshots(since: datetime | None = None) -> list[Path]:
    """Find PNG screenshots newer than `since`."""
    if not SCREENSHOTS_DIR.exists():
        log.warning("Screenshots dir not found: %s", SCREENSHOTS_DIR)
        return []

    files = sorted(SCREENSHOTS_DIR.glob("Screenshot *.png"))

    if since:
        since_ts = since.timestamp()
        files = [f for f in files if f.stat().st_mtime > since_ts]

    return files


def parse_screenshot_timestamp(path: Path) -> datetime | None:
    """Extract timestamp from 'Screenshot 2026-04-16 at 19.04.05.png'."""
    name = path.stem  # "Screenshot 2026-04-16 at 19.04.05"
    try:
        ts_str = name.replace("Screenshot ", "").replace(" at ", " ")
        return datetime.strptime(ts_str, "%Y-%m-%d %H.%M.%S").replace(tzinfo=TZ)
    except ValueError:
        return None


# ── Vision ──────────────────────────────────────────────────────────

def resize_image(path: Path) -> Path:
    """Resize to RESIZE_WIDTH using macOS sips. Returns temp file path."""
    tmp = Path(tempfile.mktemp(suffix=".png"))
    subprocess.run(
        ["sips", "--resampleWidth", str(RESIZE_WIDTH), str(path), "--out", str(tmp)],
        capture_output=True,
    )
    return tmp


def describe_screenshot(path: Path) -> dict | None:
    """Send screenshot to gemma4 vision, return structured metadata."""
    resized = resize_image(path)
    try:
        img_b64 = base64.b64encode(resized.read_bytes()).decode()
        size_kb = resized.stat().st_size // 1024

        t0 = time.time()
        project_examples_inline = ", ".join(CONFIG.personal.project_examples) or "myapp, otherapp"
        try:
            content, stats = ollama_client.chat_vision(
                render("scan_screenshots_vision", project_examples_inline=project_examples_inline),
                model=MODEL,
                image_b64=img_b64,
                timeout=TIMEOUT,
            )
        except httpx.HTTPStatusError as e:
            log.error("Ollama error %d: %s", e.response.status_code, e.response.text[:200])
            return None
        dt = time.time() - t0

        eval_count = stats.get("eval_count", 0)

        try:
            parsed = ollama_client.parse_json_lenient(content)
        except json.JSONDecodeError:
            log.warning("  Failed to parse JSON: %s", content[:200])
            parsed = None
        if not parsed:
            log.warning("  Falling back to raw text")
            parsed = {
                "app": "unknown",
                "project": None,
                "summary": content[:200],
                "key_text": "",
                "tags": [],
                "relevance": "keep",
            }

        # Ensure tags are lowercase strings
        tags = parsed.get("tags", [])
        parsed["tags"] = [str(t).lower().strip() for t in tags if t][:5]

        # Normalize relevance
        rel = parsed.get("relevance", "keep").lower()
        parsed["relevance"] = rel if rel in ("keep", "ephemeral") else "keep"

        project = parsed.get("project") or ""
        log.info("  %dKB -> %d tokens in %.1fs [%s] %s%s",
                 size_kb, eval_count, dt, parsed["relevance"],
                 parsed.get("app", "?"),
                 f" ({project})" if project else "")

        return {
            **parsed,
            "duration_s": round(dt, 1),
            "tokens": eval_count,
            "model": MODEL,
            "raw_response": content,
        }
    except httpx.TimeoutException:
        log.warning("  Timeout after %.0fs", TIMEOUT)
        return None
    except Exception as e:
        log.error("  Vision error: %s", e)
        return None
    finally:
        resized.unlink(missing_ok=True)


# ── Sidecar & Report Generation ────────────────────────────────────

def _screenshot_uri(src: Path) -> str:
    """Return a `file://` URL pointing at the original PNG in ~/Screenshots/.

    Embedded as `![](file://...)` markdown in sidecars + batch reports so
    Obsidian renders the image inline WITHOUT copying the PNG into the
    iCloud-synced vault. Mobile/iPad won't be able to load these (no access
    to ~/Screenshots/) — that's the explicit tradeoff: zero vault disk cost,
    desktop-only previews.
    """
    from urllib.parse import quote
    return "file://" + quote(str(src.resolve()))


def write_home_marker(path: Path, batch_report_slug: str | None = None) -> Path:
    """Write the slim HOME-side marker .md (next to the PNG).

    Acts purely as a skip-marker for `find_new_screenshots`. The full analysis
    lives in the batch report at `<vault>/raw/notes/screenshots/<slug>.md`;
    this marker just records *that* the PNG was scanned and *which* batch
    consumed it — no rich content duplicated here or in a parallel vault
    folder.
    """
    sidecar = path.with_suffix(".md")
    fm = [
        "---",
        f"scanned: {now_iso()}",
    ]
    if batch_report_slug:
        fm.append(f"batch_report: \"[[{batch_report_slug}]]\"")
    fm.append("---")
    body = "\nMarker file (skip-detection). Full analysis in the batch report linked above.\n"
    sidecar.write_text("\n".join(fm) + body, encoding="utf-8")
    return sidecar


def generate_batch_report(results: list[dict]) -> str:
    """Generate a batch summary report for wiki compilation."""
    # Only include "keep" screenshots in the report — ephemerals get sidecars but not wiki entries
    keeps = [r for r in results if r["meta"].get("relevance") == "keep"]
    ephemerals = len(results) - len(keeps)

    lines = [
        f"# Screenshot Batch — {now_iso()}",
        "",
        f"Processed {len(results)} screenshots with {MODEL} via {CONFIG.models.ollama_url}.",
    ]
    if ephemerals:
        lines.append(f"Skipped {ephemerals} ephemeral screenshot(s) from wiki report.")
    lines.extend([
        "",
        "| Time | App | Project | Summary | Tags |",
        "|------|-----|---------|---------|------|",
    ])
    for r in keeps:
        ts_str = r["timestamp"].strftime("%H:%M")
        m = r["meta"]
        project = m.get("project") or "-"
        tags = ", ".join(m.get("tags", []))
        summary = m.get("summary", "")[:50]
        lines.append(f"| {ts_str} | {m.get('app', '?')} | {project} | {summary} | {tags} |")

    if keeps:
        lines.extend(["", "## Details", ""])
        for r in keeps:
            ts_str = r["timestamp"].strftime("%Y-%m-%d %H:%M")
            m = r["meta"]
            project = m.get("project") or "-"
            raw_response = (m.get("raw_response") or "").strip()
            lines.append(f"### {ts_str} — `{r['file'].name}`")
            lines.append("")
            lines.append(f"![]({_screenshot_uri(r['file'])})")
            lines.append("")
            lines.append(f"- **App**: {m.get('app', '?')}")
            if project != "-":
                lines.append(f"- **Project**: {project}")
            lines.append(f"- **Summary**: {m.get('summary', '')}")
            lines.append(f"- **Key Text**: {m.get('key_text', '')}")
            lines.append(f"- **Tags**: {', '.join(m.get('tags', []))}")
            lines.append(f"- **Vision**: {m.get('model', '?')} · {m.get('tokens', 0)} tokens · {m.get('duration_s', '?')}s")
            if raw_response:
                lines.extend([
                    "",
                    "<details><summary>Raw vision response</summary>",
                    "",
                    "```json",
                    raw_response,
                    "```",
                    "",
                    "</details>",
                ])
            lines.append("")

    lines.append(f"---\n*Auto-generated by scan-screenshots.py at {now_iso()}*")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────

def scan(
    scan_all: bool = False,
    backfill_days: int | None = None,
    dry_run: bool = False,
    limit: int = MAX_PER_RUN,
) -> None:
    state = _load_state()

    # Determine scan window
    if scan_all:
        since = None
        log.info("Scanning all screenshots without sidecar")
    elif backfill_days:
        since = datetime.now(TZ) - timedelta(days=backfill_days)
        log.info("Backfill mode: last %d days (since %s)", backfill_days, since.date())
    elif "last_scan" in state:
        since = datetime.fromisoformat(state["last_scan"])
        log.info("Incremental: since %s", since.isoformat())
    else:
        since = None
        log.info("First run — scanning all screenshots without sidecar")

    # Find new screenshots — skip those that already have a sidecar .md
    screenshots = find_new_screenshots(since)
    screenshots = [s for s in screenshots if not s.with_suffix(".md").exists()]

    log.info("Found %d new screenshots", len(screenshots))

    if not screenshots:
        state["last_scan"] = now_iso()
        _save_state(state)
        return

    if limit and len(screenshots) > limit:
        log.info("Limiting to %d (of %d)", limit, len(screenshots))
        screenshots = screenshots[-limit:]  # most recent

    if dry_run:
        for s in screenshots:
            ts = parse_screenshot_timestamp(s)
            ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "?"
            print(f"  [{ts_str}] {s.name} ({s.stat().st_size // 1024}KB)")
        print(f"\n{len(screenshots)} screenshots would be processed.")
        return

    # Check Ollama connectivity
    if not ollama_client.is_reachable():
        log.error("Ollama not reachable at %s", CONFIG.models.ollama_url)
        return

    # Pre-compute the batch slug so vault sidecars can backlink to it.
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    slug = datetime.now().strftime("%Y-%m-%dT%H%M")
    batch_report_slug = f"screenshots-{slug}"

    # Process screenshots
    results = []
    for i, path in enumerate(screenshots, 1):
        ts = parse_screenshot_timestamp(path) or datetime.fromtimestamp(
            path.stat().st_mtime, tz=TZ
        )
        log.info("[%d/%d] %s", i, len(screenshots), path.name)

        meta = describe_screenshot(path)
        if not meta:
            continue

        # HOME-side slim marker (skip-detection + backlink to batch report).
        # Full analysis (incl. raw_response) lives in the batch report itself,
        # not in a parallel vault subdirectory.
        marker = write_home_marker(path, batch_report_slug=batch_report_slug)
        log.info("  Marker: %s  → batch report: %s", marker.name, batch_report_slug)

        results.append({
            "file": path,
            "timestamp": ts,
            "meta": meta,
        })

    if not results:
        log.warning("No screenshots processed successfully")
        state["last_scan"] = now_iso()
        _save_state(state)
        return

    # Write batch report for wiki compilation
    report_path = REPORT_DIR / f"{batch_report_slug}.md"
    report = generate_batch_report(results)
    report_path.write_text(report, encoding="utf-8")
    log.info("Report: %s (%d screenshots)", report_path.name, len(results))

    # Summary
    keeps = sum(1 for r in results if r["meta"].get("relevance") == "keep")
    ephemerals = len(results) - keeps
    projects = set(r["meta"].get("project") for r in results if r["meta"].get("project"))
    log.info("Relevance: %d keep, %d ephemeral", keeps, ephemerals)
    if projects:
        log.info("Projects: %s", ", ".join(sorted(projects)))

    # Update state
    state["last_scan"] = now_iso()
    state["total_processed"] = state.get("total_processed", 0) + len(results)
    _save_state(state)

    log.info("Done. %d screenshots processed, report at %s", len(results), report_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan screenshots with local LLM vision")
    parser.add_argument("--all", action="store_true", help="Scan all screenshots without sidecar (ignore time window)")
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="Scan last N days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--limit", type=int, default=MAX_PER_RUN, help=f"Max screenshots per run (default {MAX_PER_RUN})")
    args = parser.parse_args()
    scan(scan_all=getattr(args, 'all'), backfill_days=args.backfill, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
