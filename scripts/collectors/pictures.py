"""Pictures intake — folder-watching collector for camera / phone photos.

Operator drops images (iOS Shortcut, AirDrop, manual copy) into the
configured `personal.picture_inbox` directory. This collector picks them
up, runs the gemma4 vision pipeline on each, writes a batch report under
`raw/notes/pictures/` (plus a 384px thumbnail per image), and archives
the source under `<picture_inbox>/.processed/` next to a per-image
sidecar `.md` so the operator can re-find the analysis from the archive
without grepping batch reports.

Same archive-as-dedup pattern as `voice.py`; same vision pipeline as
`scan_screenshots.py` (`describe_screenshot` is imported, not duplicated).
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from collectors.scan_screenshots import describe_screenshot, make_thumbnail
from core import daily_capture, ollama_client
from core.config import CONFIG, TIMEZONE
from core.paths import RAW_DIR
from core.utils import now_iso

log = logging.getLogger(__name__)

OUTPUT_DIR = RAW_DIR / "notes" / "pictures"
THUMB_DIR = OUTPUT_DIR / "thumb"
ARCHIVE_SUBDIR = ".processed"
ACCEPTED_SUFFIXES = (".jpeg", ".jpg", ".png", ".heic")


def _inbox_path() -> Path | None:
    raw = (CONFIG.personal.picture_inbox or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _max_per_run() -> int:
    pb = CONFIG.piggybacks.get("pictures")
    return (pb.max_per_run if pb else None) or 20


def _scan_inbox(inbox: Path) -> list[Path]:
    """List eligible images in the inbox. Sorted by mtime so the oldest
    drops get processed first when a batch cap kicks in."""
    if not inbox.exists():
        return []
    items: list[Path] = []
    for p in inbox.iterdir():
        if p.is_dir():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in ACCEPTED_SUFFIXES:
            continue
        items.append(p)
    return sorted(items, key=lambda p: p.stat().st_mtime)


def _write_archive_sidecar(archive_path: Path, captured_at: datetime, meta: dict) -> None:
    """Write a per-image .md sidecar next to the archived source.

    Mirrors `scan_screenshots.write_home_sidecar` shape so the operator can
    re-find the analysis from the archive folder without grepping batch
    reports. Lives in `<picture_inbox>/.processed/` next to the JPEG.
    """
    sidecar = archive_path.with_suffix(".md")
    if sidecar.exists():
        return
    tags_str = ", ".join(meta.get("tags", []))
    ts_str = captured_at.strftime("%Y-%m-%d %H:%M")
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
        "---",
        "",
        f"# Picture {ts_str}",
        "",
        meta.get("summary", "") or "_(no summary)_",
        "",
        f"**Key Text**: {meta.get('key_text', '') or '_(none)_'}",
    ]
    if raw_response:
        fm.extend([
            "",
            "<details><summary>Raw vision response</summary>",
            "",
            "```json",
            raw_response,
            "```",
            "",
            "</details>",
        ])
    sidecar.write_text("\n".join(fm) + "\n", encoding="utf-8")


def _build_batch_report(results: list[dict], thumb_lookup: dict[str, str]) -> str:
    """Render the vault-side batch report. Same `type: screenshot-batch`
    frontmatter as `scan_screenshots` so compile.py dispatches via the
    existing lean prompt (no separate prompt needed for pictures yet)."""
    keeps = [r for r in results if r["meta"].get("relevance") == "keep"]
    ephemerals = len(results) - len(keeps)

    lines = [
        "---",
        "type: screenshot-batch",
        f"generated: {now_iso()}",
        f"screenshot_count: {len(results)}",
        "source: pictures-inbox",
        "---",
        "",
        f"# Pictures Batch — {now_iso()}",
        "",
        f"Processed {len(results)} pictures with {CONFIG.models.vision_model} via {CONFIG.models.ollama_url}.",
    ]
    if ephemerals:
        lines.append(f"Skipped {ephemerals} ephemeral picture(s) from wiki report.")
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
        summary = (m.get("summary", "") or "")[:50]
        lines.append(f"| {ts_str} | {m.get('app', '?')} | {project} | {summary} | {tags} |")

    if keeps:
        lines.extend(["", "## Details", ""])
        for r in keeps:
            ts_str = r["timestamp"].strftime("%Y-%m-%d %H:%M")
            m = r["meta"]
            project = m.get("project") or "-"
            raw_response = (m.get("raw_response") or "").strip()
            archive_name = r["archive_name"]
            lines.append(f"### {ts_str} — `{archive_name}`")
            lines.append("")
            thumb_name = thumb_lookup.get(archive_name)
            if thumb_name:
                lines.append(f"![[thumb/{thumb_name}]]")
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

    lines.append(f"---\n*Auto-generated by collectors/pictures.py at {now_iso()}*")
    return "\n".join(lines)


def _append_daily_rollup(captured_at: datetime, summary: str, archive_name: str) -> None:
    """Mirror a one-liner into daily/<date>/pictures.md so the day's
    picture-intake activity surfaces in the daily-rollup substrate.
    Failures are swallowed — never break the primary write."""
    date_iso = captured_at.strftime("%Y-%m-%d")
    time_label = captured_at.strftime("%H:%M")
    first_line = (summary or "(no summary)").strip()
    if len(first_line) > 80:
        first_line = first_line[:77].rstrip() + "…"
    line = f"- **{time_label}** · {first_line} · `{archive_name}`"
    try:
        daily_capture.append(date_iso, "pictures", line)
    except Exception:  # noqa: BLE001
        log.exception("daily-rollup append failed for picture %s", archive_name)


@register
class PicturesCollector:
    """Pictures intake — inbox-watching camera/phone-photo ingester.

    Reads accepted-suffix files from `personal.picture_inbox`, runs the
    gemma4 vision pipeline on each (via `describe_screenshot`), writes a
    `raw/notes/pictures/<batch>.md` aggregate plus per-image archive
    sidecars under `<picture_inbox>/.processed/`. No state file — the
    archive move is the dedup mechanism.

    The batch report uses `type: screenshot-batch` frontmatter on purpose:
    compile.py dispatches both screenshot- and picture-batches through the
    same lean prompt (`compile_screenshots.md`). Dedicated prompts can land
    later if the substrates diverge.
    """

    SPEC = CollectorSpec(
        name="pictures",
        output_subfolder="raw/notes/pictures",
        piggyback_default=True,
        piggyback_cooldown_hours=6,
        supports_incremental=False,
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        inbox = _inbox_path()
        return inbox is not None and inbox.exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        inbox = _inbox_path()
        if inbox is None:
            return RunResult(
                message="picture_inbox not configured (personal.picture_inbox is empty)"
            )
        if not inbox.exists():
            return RunResult(message=f"picture_inbox not found: {inbox}")

        tz = ZoneInfo(TIMEZONE)
        sources = _scan_inbox(inbox)
        if not sources:
            return RunResult(message=f"no new pictures in {inbox}")

        limit = _max_per_run()
        if limit and len(sources) > limit:
            log.info("Limiting to %d (of %d)", limit, len(sources))
            sources = sources[:limit]

        if dry_run:
            return RunResult(
                files_skipped=len(sources),
                message=f"[dry-run] would ingest {len(sources)} picture(s) from {inbox}",
            )

        if not ollama_client.is_reachable():
            return RunResult(
                message=f"Ollama not reachable at {CONFIG.models.ollama_url}"
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        archive = inbox / ARCHIVE_SUBDIR
        archive.mkdir(exist_ok=True)

        results: list[dict] = []
        thumb_lookup: dict[str, str] = {}
        errors: list[str] = []
        for i, src in enumerate(sources, 1):
            log.info("[%d/%d] %s", i, len(sources), src.name)
            meta = describe_screenshot(src)
            if not meta:
                errors.append(f"{src.name}: vision call failed")
                continue

            captured_at = datetime.fromtimestamp(src.stat().st_mtime, tz=tz)

            # Vault thumbnail (384px) before the move so make_thumbnail sees
            # the original path. Skips silently on sips errors.
            thumb = make_thumbnail(src)
            if thumb is not None:
                thumb_lookup[src.name] = thumb.name

            # Archive: source + sidecar live side-by-side under .processed/.
            archive_name = src.name
            dest = archive / archive_name
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                archive_name = f"{stem}-{int(src.stat().st_mtime)}{suffix}"
                dest = archive / archive_name
            try:
                shutil.move(str(src), str(dest))
            except OSError as exc:
                errors.append(f"{src.name}: archive failed ({exc})")
                continue

            _write_archive_sidecar(dest, captured_at, meta)
            _append_daily_rollup(captured_at, meta.get("summary", ""), archive_name)

            results.append({
                "archive_name": archive_name,
                "timestamp": captured_at,
                "meta": meta,
            })

        if not results:
            return RunResult(
                files_skipped=len(sources),
                message=f"no pictures processed successfully from {inbox}",
                errors=tuple(errors),
            )

        # Vault batch report. Slug-by-minute so concurrent fires don't clash.
        slug = datetime.now(tz).strftime("%Y-%m-%dT%H%M")
        report_path = OUTPUT_DIR / f"pictures-{slug}.md"
        report_path.write_text(_build_batch_report(results, thumb_lookup), encoding="utf-8")

        keeps = sum(1 for r in results if r["meta"].get("relevance") == "keep")
        ephemerals = len(results) - keeps
        return RunResult(
            files_written=(report_path,),
            files_skipped=len(sources) - len(results),
            message=(
                f"{len(results)} picture(s) processed "
                f"({keeps} keep, {ephemerals} ephemeral) → {report_path.name}"
            ),
            errors=tuple(errors),
        )
