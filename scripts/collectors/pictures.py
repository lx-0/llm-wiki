"""Pictures intake — folder-watching collector for camera / phone photos.

Operator drops images (iOS Shortcut, AirDrop, manual copy) into the
configured `personal.picture_inbox` directory. This collector picks them
up, runs the gemma4 vision pipeline on each (using a photo-shaped prompt
distinct from the screenshot prompt — scenes / objects / action /
text_visible instead of app / project / key_text), writes a batch report
under `raw/notes/pictures/` with `type: picture-batch` frontmatter, and
archives the source under `raw/inbox-mobile/pictures/` next to a
per-image sidecar `.md`.

The batch report shows ALL processed pictures (keep + ephemeral) so the
operator can review the vision pass; only `keep`-rated rows reach the
compile pipeline (compile.py dispatches `picture-batch` →
`compile_pictures.md`). Same archive-as-dedup pattern as voice.py.
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from collectors._picture_metadata import extract_metadata
from collectors.base import Collector, CollectorSpec, RunResult, register
from core import daily_capture, ollama_client
from core.config import CONFIG, TIMEZONE
from core.paths import RAW_DIR
from core.prompts import render, prompt_model
from core.utils import now_iso

log = logging.getLogger(__name__)

OUTPUT_DIR = RAW_DIR / "notes" / "pictures"
THUMB_DIR = OUTPUT_DIR / "thumb"
MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "pictures"
ACCEPTED_SUFFIXES = (".jpeg", ".jpg", ".png", ".heic")

MODEL = prompt_model("scan_pictures_vision", CONFIG.models.vision_model)
RESIZE_WIDTH = CONFIG.limits.screenshot_resize_width
TIMEOUT = float(CONFIG.limits.screenshot_timeout_seconds)
THUMB_WIDTH = 384  # px; matches scan_screenshots — Retina-source compromise


def _inbox_paths() -> list[Path]:
    """Resolve `personal.picture_inbox` to a list of Path objects.

    Accepts either the legacy single-string form or the multi-path list
    form (2026-05-28+). Empty strings / blanks / missing entries are
    skipped silently — the operator can leave dead entries in the list
    without breaking the scan.
    """
    raw = CONFIG.personal.picture_inbox
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    out: list[Path] = []
    for entry in items:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        if not stripped:
            continue
        out.append(Path(stripped).expanduser())
    return out


def _max_per_run() -> int:
    pb = CONFIG.piggybacks.get("pictures")
    return (pb.max_per_run if pb else None) or 20


def _make_thumbnail(src: Path) -> Path | None:
    """Generate a 384px-wide thumbnail under `raw/notes/pictures/thumb/`.

    Local copy of `scan_screenshots.make_thumbnail` — necessary because
    THE OTHER one is bound to the screenshots THUMB_DIR via its module
    constants, so importing it writes thumbs to the wrong vault folder.
    Idempotent: skips if the target exists. Returns None on sips failure
    so the batch report can omit the wikilink gracefully.
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


def _resize_image(path: Path) -> Path:
    """Resize to RESIZE_WIDTH via macOS sips; sips also transcodes HEIC →
    PNG en passant, which is what makes .heic acceptable in the inbox.
    Returns a temp PNG path."""
    tmp = Path(tempfile.mktemp(suffix=".png"))
    subprocess.run(
        ["sips", "--resampleWidth", str(RESIZE_WIDTH), str(path), "--out", str(tmp)],
        capture_output=True,
    )
    return tmp


def describe_picture(path: Path) -> dict | None:
    """Send a camera photo through gemma4 vision with the photo-shaped
    prompt. Returns the parsed metadata dict (scene_description / objects /
    action / text_visible / setting / people_present / tags / relevance)
    + vision metadata (model, tokens, duration_s, raw_response). None on
    timeout / HTTP error / unrecoverable parse failure."""
    resized = _resize_image(path)
    try:
        img_b64 = base64.b64encode(resized.read_bytes()).decode()
        size_kb = resized.stat().st_size // 1024

        t0 = time.time()
        try:
            content, stats = ollama_client.chat_vision(
                render("scan_pictures_vision"),
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
                "scene_description": content[:300],
                "setting": None,
                "objects": [],
                "action": None,
                "text_visible": None,
                "people_present": False,
                "tags": [],
                "relevance": "ephemeral",
            }

        # Normalize shape
        tags = parsed.get("tags") or []
        parsed["tags"] = [str(t).lower().strip() for t in tags if t][:5]
        objects = parsed.get("objects") or []
        parsed["objects"] = [str(o).lower().strip() for o in objects if o][:7]
        rel = (parsed.get("relevance") or "ephemeral").lower()
        parsed["relevance"] = rel if rel in ("keep", "ephemeral") else "ephemeral"
        people = parsed.get("people_present")
        parsed["people_present"] = bool(people) if people is not None else False

        log.info("  %dKB -> %d tokens in %.1fs [%s] %s",
                 size_kb, eval_count, dt, parsed["relevance"],
                 (parsed.get("setting") or parsed.get("scene_description") or "?")[:60])

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
    except Exception as e:  # noqa: BLE001
        log.error("  Vision error: %s", e)
        return None
    finally:
        resized.unlink(missing_ok=True)


def _scan_inbox(inbox: Path) -> list[Path]:
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


def _render_picture_metadata_block(picture_metadata: dict) -> list[str]:
    """Render the optional deterministic-metadata frontmatter keys
    (`device`, `location`, `shot`, `app_context`) as YAML lines. Empty
    sub-dicts and missing keys are skipped so the sidecar only carries
    fields that are actually populated for the source file."""
    lines: list[str] = []
    device = picture_metadata.get("device") or {}
    if device:
        lines.append("device:")
        for k, v in device.items():
            lines.append(f"  {k}: {json.dumps(v)}")
    location = picture_metadata.get("location") or {}
    if location:
        lines.append("location:")
        for k, v in location.items():
            lines.append(f"  {k}: {v}")
    shot = picture_metadata.get("shot") or {}
    if shot:
        lines.append("shot:")
        for k, v in shot.items():
            if isinstance(v, str):
                lines.append(f"  {k}: {json.dumps(v)}")
            else:
                lines.append(f"  {k}: {v}")
    app_context = picture_metadata.get("app_context")
    if isinstance(app_context, str) and app_context.strip():
        lines.append(f"app_context: {json.dumps(app_context.strip())}")
    return lines


def _write_archive_sidecar(
    archive_path: Path,
    captured_at: datetime,
    meta: dict,
    picture_metadata: dict | None = None,
) -> None:
    """Write a per-image sidecar next to the archived source so the
    operator can re-find the analysis from the archive folder without
    grepping batch reports. Picture-shaped fields."""
    sidecar = archive_path.with_suffix(".md")
    if sidecar.exists():
        return
    ts_str = captured_at.strftime("%Y-%m-%d %H:%M")
    tags_str = ", ".join(meta.get("tags", []))
    objects_str = ", ".join(meta.get("objects", []))
    setting = meta.get("setting") or ""
    action = meta.get("action") or ""
    text_visible = meta.get("text_visible") or ""
    raw_response = (meta.get("raw_response") or "").strip()

    fm = [
        "---",
        f"captured_at: {captured_at.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"setting: {json.dumps(setting) if setting else 'null'}",
        f"action: {json.dumps(action) if action else 'null'}",
        f"objects: [{objects_str}]",
        f"tags: [{tags_str}]",
        f"people_present: {str(meta.get('people_present', False)).lower()}",
        f"relevance: {meta.get('relevance', 'ephemeral')}",
        f"scanned: {now_iso()}",
        f"vision_model: {json.dumps(meta.get('model', ''))}",
        f"vision_tokens: {int(meta.get('tokens', 0) or 0)}",
    ]
    fm.extend(_render_picture_metadata_block(picture_metadata or {}))
    fm.extend([
        "---",
        "",
        f"# Picture {ts_str}",
        "",
        meta.get("scene_description", "") or "_(no description)_",
        "",
        f"**Text visible**: {text_visible or '_(none)_'}",
    ])
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
    """Render the vault-side batch report. `type: picture-batch` is
    dispatched by compile.py to `compile_pictures.md` (Haiku, 20 turns).

    All rows are shown in the report — keep + ephemeral — so the operator
    can review the vision pass without opening archive sidecars. compile
    consumes only the `keep` rows (per the compile prompt's filter step)."""
    keeps = [r for r in results if r["meta"].get("relevance") == "keep"]
    ephemerals = [r for r in results if r["meta"].get("relevance") != "keep"]

    lines = [
        "---",
        "type: picture-batch",
        f"generated: {now_iso()}",
        f"picture_count: {len(results)}",
        f"keep_count: {len(keeps)}",
        f"ephemeral_count: {len(ephemerals)}",
        "---",
        "",
        f"# Pictures Batch — {now_iso()}",
        "",
        f"Processed {len(results)} picture(s) with {MODEL} via {CONFIG.models.ollama_url}.",
        f"Vision pass: {len(keeps)} keep · {len(ephemerals)} ephemeral.",
        "",
        "| Time | Setting | Scene | Text visible | Tags | Relevance |",
        "|------|---------|-------|--------------|------|-----------|",
    ]
    for r in results:
        ts_str = r["timestamp"].strftime("%H:%M")
        m = r["meta"]
        setting = (m.get("setting") or "-")[:30]
        scene = (m.get("scene_description") or "")[:60]
        text = (m.get("text_visible") or "")[:40]
        tags = ", ".join(m.get("tags", []))
        rel = m.get("relevance", "?")
        lines.append(f"| {ts_str} | {setting} | {scene} | {text} | {tags} | {rel} |")

    # Detail blocks for keeps only — these are the rows compile_pictures
    # will look at. Ephemerals are summarized in the table for operator
    # awareness but get no detail block (matches the compile filter step).
    if keeps:
        lines.extend(["", "## Details (keep)", ""])
        for r in keeps:
            ts_str = r["timestamp"].strftime("%Y-%m-%d %H:%M")
            m = r["meta"]
            archive_name = r["archive_name"]
            raw_response = (m.get("raw_response") or "").strip()
            lines.append(f"### {ts_str} — `{archive_name}`")
            lines.append("")
            thumb_name = thumb_lookup.get(archive_name)
            if thumb_name:
                lines.append(f"![[thumb/{thumb_name}]]")
                lines.append("")
            lines.append(f"- **Scene**: {m.get('scene_description', '')}")
            if m.get("setting"):
                lines.append(f"- **Setting**: {m.get('setting')}")
            if m.get("action"):
                lines.append(f"- **Action**: {m.get('action')}")
            if m.get("objects"):
                lines.append(f"- **Objects**: {', '.join(m['objects'])}")
            if m.get("text_visible"):
                lines.append(f"- **Text visible**: {m['text_visible']}")
            lines.append(f"- **People present**: {m.get('people_present', False)}")
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


def _append_daily_rollup(captured_at: datetime, scene: str, archive_name: str) -> None:
    """Mirror a one-liner into daily/<date>/pictures.md. Failures are
    swallowed — never break the primary write."""
    date_iso = captured_at.strftime("%Y-%m-%d")
    time_label = captured_at.strftime("%H:%M")
    first_line = (scene or "(no description)").strip()
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
    photo-shaped vision pipeline on each (via `describe_picture`), writes
    a `raw/notes/pictures/<batch>.md` aggregate (`type: picture-batch`)
    + per-image archive sidecars under `raw/inbox-mobile/pictures/`. No
    state file — the archive move is the dedup mechanism.

    compile.py dispatches `picture-batch` → `compile_pictures.md` (Haiku,
    20 turns) — picture-shaped extraction rules, ruthless anti-noise
    filter (most camera photos do NOT become knowledge entries).
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
        return any(p.exists() for p in _inbox_paths())

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        inboxes = _inbox_paths()
        if not inboxes:
            return RunResult(
                message="picture_inbox not configured (personal.picture_inbox is empty)"
            )

        tz = ZoneInfo(TIMEZONE)
        sources: list[Path] = []
        missing: list[Path] = []
        for inbox in inboxes:
            if not inbox.exists():
                missing.append(inbox)
                continue
            sources.extend(_scan_inbox(inbox))
        # Re-sort across inboxes by mtime so the batch report reads
        # chronologically regardless of which inbox a file came from.
        sources.sort(key=lambda p: p.stat().st_mtime)

        if missing:
            log.warning("picture_inbox: %d configured path(s) not found: %s",
                        len(missing), ", ".join(str(p) for p in missing))
        if not sources:
            label = inboxes[0] if len(inboxes) == 1 else f"{len(inboxes)} configured inbox(es)"
            return RunResult(message=f"no new pictures in {label}")

        limit = _max_per_run()
        if limit and len(sources) > limit:
            log.info("Limiting to %d (of %d)", limit, len(sources))
            sources = sources[:limit]

        if dry_run:
            label = inboxes[0] if len(inboxes) == 1 else f"{len(inboxes)} inbox(es)"
            return RunResult(
                files_skipped=len(sources),
                message=f"[dry-run] would ingest {len(sources)} picture(s) from {label}",
            )

        if not ollama_client.is_reachable():
            return RunResult(
                message=f"Ollama not reachable at {CONFIG.models.ollama_url}"
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        MOBILE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        results: list[dict] = []
        thumb_lookup: dict[str, str] = {}
        errors: list[str] = []
        extract_picture_metadata = getattr(
            CONFIG.features, "extract_picture_metadata", True
        )

        for i, src in enumerate(sources, 1):
            log.info("[%d/%d] %s", i, len(sources), src.name)

            # Deterministic metadata first — captured_at from EXIF /
            # filename pattern is more accurate than the source's mtime
            # (which is post-Drive-sync / post-bridge-copy time).
            picture_metadata: dict = {}
            if extract_picture_metadata:
                try:
                    picture_metadata = extract_metadata(src)
                except Exception:  # noqa: BLE001
                    log.exception("metadata extraction failed for %s", src.name)
                    picture_metadata = {}

            meta = describe_picture(src)
            if not meta:
                errors.append(f"{src.name}: vision call failed")
                continue

            captured_at_dt = picture_metadata.get("captured_at")
            if isinstance(captured_at_dt, datetime):
                # EXIF / filename timestamps are naive — attach the engine
                # timezone so downstream daily/-rollup bucketing is correct.
                if captured_at_dt.tzinfo is None:
                    captured_at_dt = captured_at_dt.replace(tzinfo=tz)
                captured_at = captured_at_dt
            else:
                captured_at = datetime.fromtimestamp(src.stat().st_mtime, tz=tz)

            thumb = _make_thumbnail(src)
            if thumb is not None:
                thumb_lookup[src.name] = thumb.name

            archive_name = src.name
            dest = MOBILE_ARCHIVE_DIR / archive_name
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                archive_name = f"{stem}-{int(src.stat().st_mtime)}{suffix}"
                dest = MOBILE_ARCHIVE_DIR / archive_name
            try:
                shutil.move(str(src), str(dest))
            except OSError as exc:
                errors.append(f"{src.name}: archive failed ({exc})")
                continue

            _write_archive_sidecar(dest, captured_at, meta, picture_metadata)
            _append_daily_rollup(captured_at, meta.get("scene_description", ""), archive_name)

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
