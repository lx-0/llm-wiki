"""
Scan ~/Screenshots/ for new screenshots, describe them with local LLM (gemma4 vision),
and save as raw notes for wiki compilation.

Runs as a daily piggyback task. Tracks last scan timestamp in state file.

Usage:
    uv run python scripts/collectors/scan-screenshots.py                    # scan new screenshots
    uv run python scripts/collectors/scan-screenshots.py --all               # all without sidecar
    uv run python scripts/collectors/scan-screenshots.py --all --limit 50    # batch of 50
    uv run python scripts/collectors/scan-screenshots.py --backfill 7        # last 7 days
    uv run python scripts/collectors/scan-screenshots.py --dry-run            # show what would be processed
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402  exception types only; HTTP via ollama_client

from collectors.base import Collector, CollectorSpec, RunResult, register
from core import ollama_client
from core.paths import RAW_DIR, ROOT_DIR, STATE_DIR
from core.config import CONFIG, TIMEZONE
from core.utils import load_json_state, now_iso, save_json_state

# ── Config ──────────────────────────────────────────────────────────

SCREENSHOTS_DIR = Path.home() / "Screenshots"
REPORT_DIR = RAW_DIR / "notes" / "screenshots"
THUMB_DIR = REPORT_DIR / "thumb"
THUMB_WIDTH = 384  # px; ~60-80KB per Retina-source screenshot — compromise between text legibility and iCloud cost
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "screenshot-state.json"

MODEL = CONFIG.models.vision_model
RESIZE_WIDTH = CONFIG.limits.screenshot_resize_width
_screenshot_pb = CONFIG.piggybacks.get("screenshots")
MAX_PER_RUN = (_screenshot_pb.max_per_run if _screenshot_pb else None) or 50
TIMEOUT = float(CONFIG.limits.screenshot_timeout_seconds)

TZ = ZoneInfo(TIMEZONE)

log = logging.getLogger("scan-screenshots")

from core.prompts import render  # noqa: E402


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

    files = sorted(SCREENSHOTS_DIR.glob("*.png"))

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

def make_thumbnail(src: Path) -> Path | None:
    """Generate a deterministic vault-side thumbnail of the original PNG.

    512px-wide PNG written to `<vault>/raw/notes/screenshots/thumb/<name>.png`
    via macOS `sips`. Idempotent: skips if the target already exists. The
    thumbnail is the only image asset that lives inside the vault — original
    PNGs stay in ~/Screenshots/, never copied. Embed in batch reports via
    Obsidian wikilink (`![[thumb/<name>.png]]`) — works on mobile + desktop,
    syncs via iCloud (~30-50 KB per typical screenshot).

    Returns None on failure (sips not available, src missing).
    """
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    dst = THUMB_DIR / src.name
    if dst.exists():
        return dst
    try:
        proc = subprocess.run(
            ["sips", "--resampleWidth", str(THUMB_WIDTH), str(src), "--out", str(dst)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            log.warning("  thumbnail failed (%d): %s", proc.returncode, proc.stderr.strip()[:200])
            return None
        return dst
    except FileNotFoundError:
        log.warning("  sips not available — skipping thumbnail for %s", src.name)
        return None


def write_home_sidecar(
    path: Path,
    ts: datetime,
    meta: dict,
    batch_report_slug: str | None = None,
) -> Path:
    """Write the rich HOME-side sidecar .md next to the PNG.

    This is THE per-screenshot analysis archive — single source of truth.
    Frontmatter holds app/project/tags/relevance/scanned plus vision metadata
    (model, tokens). Body has summary, key_text, and the raw LLM response in
    a collapsible `<details>` block for audit / debug. Lives next to the
    original PNG so the operator browsing ~/Screenshots/ in Finder gets a
    "what was this?" answer without opening the vault.

    The vault batch report is a roll-up aggregate of all sidecars in a scan
    run — written from the same in-memory `meta` dict, never re-analyzed.
    """
    sidecar = path.with_suffix(".md")
    tags_str = ", ".join(meta.get("tags", []))
    ts_str = ts.strftime("%Y-%m-%d %H:%M")
    project = meta.get("project") or ""
    raw_response = (meta.get("raw_response") or "").strip()
    app = meta.get("app", "unknown")

    fm = [
        "---",
        f"app: {json.dumps(app)}",
        f"project: {json.dumps(project) if project else 'null'}",
        f"tags: [{tags_str}]",
        f"relevance: {meta.get('relevance', 'keep')}",
        f"scanned: {now_iso()}",
        f"vision_model: {json.dumps(meta.get('model', ''))}",
        f"vision_tokens: {int(meta.get('tokens', 0) or 0)}",
    ]
    if batch_report_slug:
        fm.append(f"batch_report: \"[[{batch_report_slug}]]\"")
    fm.append("---")

    body = [
        "",
        f"# Screenshot {ts_str}",
        "",
        meta.get("summary", "") or "_(no summary)_",
        "",
        f"**Key Text**: {meta.get('key_text', '') or '_(none)_'}",
    ]
    if raw_response:
        body.extend([
            "",
            "<details><summary>Raw vision response</summary>",
            "",
            "```json",
            raw_response,
            "```",
            "",
            "</details>",
        ])
    sidecar.write_text("\n".join(fm + body) + "\n", encoding="utf-8")
    return sidecar


def generate_batch_report(results: list[dict]) -> str:
    """Generate a batch summary report for wiki compilation."""
    # Only include "keep" screenshots in the report — ephemerals get sidecars but not wiki entries
    keeps = [r for r in results if r["meta"].get("relevance") == "keep"]
    ephemerals = len(results) - len(keeps)

    # Frontmatter `type: screenshot-batch` lets compile.py dispatch via
    # SUBSTRATE_PROMPTS to the lean compile_screenshots prompt + Haiku,
    # instead of falling through to compile_main.md (which hits max_turns
    # at $5+/file on 50-screenshot batches — see KNOWLEDGE.md
    # "substrate-prompt mismatch on screenshot batches" 2026-05-16).
    lines = [
        "---",
        "type: screenshot-batch",
        f"generated: {now_iso()}",
        f"screenshot_count: {len(results)}",
        "---",
        "",
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
            lines.append(f"![[thumb/{r['file'].name}]]")
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
) -> dict:
    """Scan screenshots, write sidecars + batch report.

    Returns a result dict: ``{"processed": int, "report_path": Path | None,
    "message": str}``. The CLI ignores it; the Collector wrapper maps it
    onto a RunResult.
    """
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
        return {"processed": 0, "report_path": None, "message": "no new screenshots"}

    if limit and len(screenshots) > limit:
        log.info("Limiting to %d (of %d)", limit, len(screenshots))
        screenshots = screenshots[-limit:]  # most recent

    if dry_run:
        for s in screenshots:
            ts = parse_screenshot_timestamp(s)
            ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "?"
            print(f"  [{ts_str}] {s.name} ({s.stat().st_size // 1024}KB)")
        print(f"\n{len(screenshots)} screenshots would be processed.")
        return {"processed": 0, "report_path": None,
                "message": f"[dry-run] {len(screenshots)} screenshot(s) would be processed"}

    # Check Ollama connectivity
    if not ollama_client.is_reachable():
        log.error("Ollama not reachable at %s", CONFIG.models.ollama_url)
        return {"processed": 0, "report_path": None,
                "message": f"Ollama not reachable at {CONFIG.models.ollama_url}"}

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

        # HOME sidecar = the analysis (rich, with raw_response). Single source
        # of truth per screenshot. Batch report aggregates all sidecars in this
        # run for compile-pipeline consumption.
        sidecar = write_home_sidecar(path, ts, meta, batch_report_slug=batch_report_slug)
        # Vault thumbnail (512px PNG) so the batch report can preview inline.
        thumb = make_thumbnail(path)
        log.info("  Sidecar: %s  Thumb: %s",
                 sidecar.name, thumb.name if thumb else "skipped")

        results.append({
            "file": path,
            "timestamp": ts,
            "meta": meta,
        })

    if not results:
        log.warning("No screenshots processed successfully")
        state["last_scan"] = now_iso()
        _save_state(state)
        return {"processed": 0, "report_path": None,
                "message": "no screenshots processed successfully"}

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
    return {
        "processed": len(results),
        "report_path": report_path,
        "message": f"{len(results)} screenshot(s) processed ({keeps} keep, {ephemerals} ephemeral) → {report_path.name}",
    }


def backfill_thumbnails(dry_run: bool = False) -> None:
    """Generate vault-side thumbnails for every PNG in ~/Screenshots/ that
    doesn't have one yet. No LLM calls. One-shot retrofit so historical
    batch reports can also embed `![[thumb/<name>.png]]`.
    """
    if not SCREENSHOTS_DIR.exists():
        log.error("Screenshots dir not found: %s", SCREENSHOTS_DIR)
        return
    pngs = sorted(SCREENSHOTS_DIR.glob("Screenshot *.png"))
    log.info("Backfill thumbnails: scanning %d PNGs", len(pngs))
    made = skipped = errors = 0
    for png in pngs:
        target = THUMB_DIR / png.name
        if target.exists():
            skipped += 1
            continue
        if dry_run:
            log.info("  [dry] would thumb %s", png.name)
            made += 1
            continue
        if make_thumbnail(png):
            made += 1
            if made % 50 == 0:
                log.info("  ... %d thumbnails", made)
        else:
            errors += 1
    log.info("Backfill thumbnails: %d made, %d already-present, %d errors",
             made, skipped, errors)


def retrofit_batch_reports(dry_run: bool = False) -> None:
    """Add ``![[thumb/<filename>]]`` lines under each ``### {ts} — `<file>.png```
    heading in existing batch reports. Idempotent: skips reports that already
    have the embed line. Safe to re-run.
    """
    if not REPORT_DIR.exists():
        log.error("Report dir not found: %s", REPORT_DIR)
        return
    reports = sorted(REPORT_DIR.glob("screenshots-*.md"))
    log.info("Retrofit: scanning %d batch reports", len(reports))
    import re
    pattern = re.compile(r"^### (.+?) — `(Screenshot [^`]+\.png)`\s*$", re.MULTILINE)
    patched = skipped = 0
    for report in reports:
        text = report.read_text(encoding="utf-8")
        def repl(m: re.Match) -> str:
            head = m.group(0)
            fname = m.group(2)
            embed = f"![[thumb/{fname}]]"
            if embed in text:  # already retrofit at some other location
                return head
            return f"{head}\n\n{embed}"
        new_text = pattern.sub(repl, text)
        # Skip if no real change OR if embed lines already present at all positions
        embed_count_before = text.count("![[thumb/")
        embed_count_after = new_text.count("![[thumb/")
        if embed_count_after > embed_count_before:
            if not dry_run:
                report.write_text(new_text, encoding="utf-8")
            log.info("  patched %s (+%d embeds)", report.name,
                     embed_count_after - embed_count_before)
            patched += 1
        else:
            skipped += 1
    log.info("Retrofit: %d patched, %d already-present", patched, skipped)


# ── Collector wrapper ───────────────────────────────────────────────


@register
class ScreenshotsCollector:
    """~/Screenshots/ → vision-LLM → raw/notes/screenshots/ — Collector Protocol wrapper.

    The one Collector with an LLM sub-step: each PNG goes through gemma4
    vision once, producing a HOME sidecar + 384px vault thumbnail + an
    entry in the run's batch report. `is_configured()` only checks the
    screenshots dir — Ollama reachability is checked inside `scan()` and
    degrades gracefully (returns a no-op result, never crashes).

    This Collector REPLACES the legacy `_LEGACY_PIGGYBACK_COMMANDS`
    "scan_screenshots" entry (now in `core/piggybacks.py`) —
    `piggyback_default=True` makes the Registry walk auto-discover it. The
    piggyback config key is
    `piggybacks.screenshots` (renamed from `scan_screenshots` for naming
    consistency with the other Registry collectors).
    """

    SPEC = CollectorSpec(
        name="screenshots",
        output_subfolder="raw/notes/screenshots",
        piggyback_default=True,  # was a daily piggyback in the legacy hardcoded list
        piggyback_cooldown_hours=24,
        supports_incremental=False,  # run() always does the "all without sidecar" sweep
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        """True iff ~/Screenshots/ exists. Ollama reachability is a runtime concern."""
        return SCREENSHOTS_DIR.exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self.is_configured():
            return RunResult(message=f"Screenshots dir not found: {SCREENSHOTS_DIR}")

        # scan_all=True mirrors the legacy piggyback invocation
        # (`--all --limit {max_per_run}`): process every PNG without a
        # sidecar, capped at MAX_PER_RUN. The state-file time window is a
        # CLI-only mode (the no-flag default of the direct script).
        result = scan(scan_all=True, dry_run=dry_run, limit=MAX_PER_RUN)
        report_path = result.get("report_path")
        return RunResult(
            files_written=(report_path,) if report_path else (),
            files_skipped=0 if report_path else 1,
            message=result.get("message", ""),
        )


# ── Direct CLI entry (backward-compat) ──────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan screenshots with local LLM vision")
    parser.add_argument("--all", action="store_true", help="Scan all screenshots without sidecar (ignore time window)")
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="Scan last N days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--limit", type=int, default=MAX_PER_RUN, help=f"Max screenshots per run (default {MAX_PER_RUN})")
    parser.add_argument("--backfill-thumbnails", action="store_true",
                        help="Generate vault thumbnails for every PNG without one (no LLM)")
    parser.add_argument("--retrofit-batch-reports", action="store_true",
                        help="Add ![[thumb/...]] embeds to existing batch reports")
    args = parser.parse_args()
    if getattr(args, 'backfill_thumbnails'):
        backfill_thumbnails(dry_run=args.dry_run)
    elif getattr(args, 'retrofit_batch_reports'):
        retrofit_batch_reports(dry_run=args.dry_run)
    else:
        scan(scan_all=getattr(args, 'all'), backfill_days=args.backfill, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    # Module-level basicConfig was polluting the root logger whenever
    # `collectors/__init__.py` import-chained into this module — flush.py's
    # subsequent basicConfig became a no-op, silently shunting all its
    # logging to stderr (and to DEVNULL when spawned as a piggyback). Keep
    # logging setup local to the standalone-script entry point.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    main()
