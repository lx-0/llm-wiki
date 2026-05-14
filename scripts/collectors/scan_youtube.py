"""
Scan YouTube URLs (single video, playlist, or inbox-list) and write tiered
metadata + transcript + comments into raw/notes/youtube/.

First-aufschlag scope: Tier 0 (yt-dlp metadata), Tier 1 (subtitles via
youtube-transcript-api with yt-dlp fallback), Tier 2 (top comments via
yt-dlp). All free, no LLM. Tier 3 (gemma4 frame-sampling / Gemini cloud)
is a follow-up — see .ytstack/backlog/youtube-intake.md.

Wired in two ways:
  - As a Registry-discovered Collector: `wiki collect youtube`. The
    `@register` decorator below adds `YoutubeCollector` to the Registry.
    The Collector's `run()` is the inbox-drain mode — it processes
    `raw/inbox/youtube.md` (a markdown URL list). The rich per-URL flags
    (`--url` / `--tier` / `--no-skip`) are CLI-only, same as calendar's
    `--year` and browser's `--source`.
  - As a direct CLI: `uv run python scripts/collectors/scan_youtube.py
    --url URL [--tier N]` (also wrapped by `wiki ingest-youtube`).
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from core.paths import RAW_DIR
from core.utils import now_iso
from core.config import CONFIG

# yt-dlp + youtube-transcript-api are imported lazily so --help works
# without the deps installed.

REPORT_DIR = RAW_DIR / "notes" / "youtube"
INBOX_FILE = RAW_DIR / "inbox" / "youtube.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("scan-youtube")


# ── URL parsing ──────────────────────────────────────────────────────

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/shorts/|/embed/|/watch\?v=)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video id from any YouTube URL form."""
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def is_playlist_url(url: str) -> bool:
    return "list=" in url


# ── Inbox-line parser ────────────────────────────────────────────────

_LINE_TIER_RE = re.compile(r"\btier\s*[:=]\s*([0-4])\b", re.IGNORECASE)
_LINE_URL_RE = re.compile(r"https?://[^\s)\]]+")


@dataclass
class InboxItem:
    url: str
    note: str | None = None
    tier_override: int | None = None


def parse_inbox(text: str) -> list[InboxItem]:
    """Parse an unformatted markdown list of YouTube URLs.

    Robust to: bare URLs, markdown links [title](url), youtu.be shortlinks,
    mobile m.youtube.com, &t=... timestamps, optional inline note after URL,
    optional `tier: N` directive in the note.
    """
    items: list[InboxItem] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_URL_RE.search(line)
        if not m:
            continue
        url = m.group(0).rstrip(".,;:")
        if "youtube.com" not in url and "youtu.be" not in url:
            continue
        rest = (line[: m.start()] + line[m.end() :]).strip(" -*[](),:")
        tier_m = _LINE_TIER_RE.search(rest)
        tier_override = int(tier_m.group(1)) if tier_m else None
        if tier_m:
            rest = (rest[: tier_m.start()] + rest[tier_m.end() :]).strip(" -,:")
        items.append(InboxItem(url=url, note=rest or None, tier_override=tier_override))
    return items


# ── yt-dlp metadata + playlist expansion ─────────────────────────────

def _ydl(extra_opts: dict | None = None):
    """Return a configured YoutubeDL instance."""
    from yt_dlp import YoutubeDL  # type: ignore

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    if extra_opts:
        opts.update(extra_opts)
    return YoutubeDL(opts)


_LIST_PARAM_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")


def _normalize_playlist_url(url: str) -> str:
    """`watch?v=...&list=L` → `playlist?list=L` so yt-dlp sees the whole list."""
    m = _LIST_PARAM_RE.search(url)
    if not m:
        return url
    return f"https://www.youtube.com/playlist?list={m.group(1)}"


def expand_playlist(url: str, limit: int | None = None) -> list[str]:
    """Return individual video URLs from a playlist (or [url] for a single video)."""
    if not is_playlist_url(url):
        return [url]
    log.info("Expanding playlist (limit=%s)", limit)
    norm_url = _normalize_playlist_url(url)
    with _ydl({"extract_flat": True}) as ydl:
        info = ydl.extract_info(norm_url, download=False)
    entries = info.get("entries") or []
    urls: list[str] = []
    for e in entries:
        vid = e.get("id") or e.get("url")
        if vid:
            urls.append(f"https://www.youtube.com/watch?v={vid}")
        if limit and len(urls) >= limit:
            break
    log.info("Playlist contains %d videos (using %d)", len(entries), len(urls))
    return urls


def fetch_metadata(url: str, *, with_comments: bool = False) -> dict:
    """Tier-0 + optional Tier-2: yt-dlp metadata, optionally with comments."""
    extra = {"getcomments": True, "extractor_args": {"youtube": {"max_comments": ["50", "all", "50"]}}} if with_comments else {}
    with _ydl(extra) as ydl:
        info = ydl.extract_info(url, download=False)
    return info  # raw yt-dlp dict; we slim it down at write time


# ── Transcript ───────────────────────────────────────────────────────

def fetch_transcript(video_id: str, *, languages: tuple[str, ...] = ("en", "de")) -> dict | None:
    """Tier-1: transcript via youtube-transcript-api, with yt-dlp auto-sub fallback."""
    # Primary: youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=list(languages))
        segments = [
            {"start_s": round(s.start, 2), "duration_s": round(s.duration, 2), "text": s.text}
            for s in transcript.snippets
        ]
        return {
            "language": transcript.language_code,
            "is_generated": transcript.is_generated,
            "source": "youtube-transcript-api",
            "segments": segments,
            "plain": " ".join(s["text"] for s in segments),
        }
    except Exception as e:  # noqa: BLE001
        log.info("transcript-api failed for %s (%s); trying yt-dlp fallback", video_id, type(e).__name__)

    # Fallback: yt-dlp auto-subs
    return _fetch_transcript_ytdlp(video_id, languages=languages)


def _fetch_transcript_ytdlp(video_id: str, *, languages: tuple[str, ...]) -> dict | None:
    """yt-dlp fallback for transcript fetch — handles cases where the API library
    returns TranscriptsDisabled but yt-dlp can still pull auto-captions."""
    import tempfile

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(languages),
            "subtitlesformat": "json3",
            "outtmpl": str(Path(tmp) / "%(id)s"),
        }
        try:
            from yt_dlp import YoutubeDL  # type: ignore

            with YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)  # writes sub files only
        except Exception as e:  # noqa: BLE001
            log.warning("yt-dlp fallback failed for %s: %s", video_id, type(e).__name__)
            return None

        # Find first available .json3 sub file (preference order = languages tuple)
        for lang in languages:
            for suffix in (lang, f"{lang}-orig", f"{lang}-auto"):
                candidates = list(Path(tmp).glob(f"*.{suffix}.json3"))
                if candidates:
                    return _parse_json3(candidates[0], lang)
        # Catch-all: any json3 file at all
        any_json3 = list(Path(tmp).glob("*.json3"))
        if any_json3:
            # Filename pattern: <id>.<lang>.json3
            stem = any_json3[0].stem
            lang = stem.split(".")[-1] if "." in stem else "unknown"
            return _parse_json3(any_json3[0], lang)
        log.warning("yt-dlp wrote no subtitle files for %s", video_id)
        return None


def _parse_json3(path: Path, lang: str) -> dict:
    """Parse a YouTube .json3 caption file into our segment shape."""
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
        if not text:
            continue
        start_ms = ev.get("tStartMs", 0)
        dur_ms = ev.get("dDurationMs", 0)
        segments.append({
            "start_s": round(start_ms / 1000, 2),
            "duration_s": round(dur_ms / 1000, 2),
            "text": text,
        })
    return {
        "language": lang,
        "is_generated": True,  # yt-dlp fallback path is auto-only here
        "source": "yt-dlp-json3",
        "segments": segments,
        "plain": " ".join(s["text"] for s in segments),
    }


# ── Comment slimming ─────────────────────────────────────────────────

def slim_comments(raw_comments: list[dict] | None, *, top_n: int = 20) -> list[dict]:
    """Filter comments to high-signal subset.

    Keeps creator-responses + top-N by like_count. Strips noise fields.
    """
    if not raw_comments:
        return []
    creator = [c for c in raw_comments if c.get("author_is_uploader")]
    rest = [c for c in raw_comments if not c.get("author_is_uploader")]
    rest.sort(key=lambda c: c.get("like_count") or 0, reverse=True)
    picked = creator + rest[:top_n]

    def trim(c: dict) -> dict:
        return {
            "author": c.get("author"),
            "text": c.get("text"),
            "like_count": c.get("like_count"),
            "is_creator": bool(c.get("author_is_uploader")),
            "is_reply": bool(c.get("parent")),
            "published_at": c.get("timestamp"),
        }

    return [trim(c) for c in picked]


# ── Tier 3-local: ffmpeg frame sampling + gemma4 vision ──────────────

FRAME_PROMPT = """You are analyzing ONE FRAME from a YouTube video for a knowledge wiki.

In 2-4 sentences, describe:
- What is shown (slide title, code on screen, diagram, terminal, IDE, talking head, blank/transition).
- Any readable text — transcribe key text verbatim. For code on screen, copy what you can read.
- Visual concepts (UI elements visible, formulas, chart axes, architecture-diagram boxes).

Rules:
- Be concrete. No "the speaker discusses something interesting".
- If the frame is uninformative (transition, talking-head with no slide, blank), reply with the single word: UNINFORMATIVE.
- No greetings, no preamble, just the description."""


AGGREGATE_PROMPT_TEMPLATE = """You are writing a knowledge-wiki entry about this YouTube video. Output Markdown only — no preamble.

# Source

- Title: {title}
- Channel: {channel}
- Duration: {duration_min} min
- Upload date: {upload_date}

# Transcript (subtitles)

{transcript_block}

# Per-frame visual analysis (chronological)

{frames_block}

# Your task

Synthesize into Markdown sections (use these exact headers):

## Key concepts

3-7 bullets, each one short concrete claim grounded in transcript or visual.

## Visual artifacts

Slides / diagrams / charts / IDE-content shown. List them with timestamps `[mm:ss]` from the per-frame log. Skip frames marked UNINFORMATIVE.

## Code on screen

Any code visible in frames — fenced blocks with language tag where you can detect it. If none was visible, write "(none captured)".

## Audio-visual divergence

Cases where the visual shows something the transcript doesn't cover (or vice versa). One bullet per divergence with the timestamp. If transcript is missing, treat the entire visual track as new information."""


def _ts_to_label(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def pick_frame_timestamps(metadata: dict) -> tuple[list[float], str]:
    """Return (timestamps_in_seconds, strategy_name).

    Strategy: chapter-aligned (mid-of-chapter) when ≥3 chapters; else fixed
    interval evenly spread across duration; capped at CONFIG.limits.youtube_max_frames.
    """
    duration = float(metadata.get("duration_s") or 0)
    if duration <= 0:
        return [], "no-duration"

    max_frames = CONFIG.limits.youtube_max_frames

    chapters = metadata.get("chapters") or []
    if len(chapters) >= 3:
        timestamps = []
        for ch in chapters:
            start = float(ch.get("start_time") or 0)
            end = float(ch.get("end_time") or start + 30)
            timestamps.append((start + end) / 2)
        return timestamps[:max_frames], "chapter-aligned"

    # Fixed interval: ~one frame per 60s, capped
    n_frames = min(max_frames, max(5, int(duration // 60)))
    step = duration / (n_frames + 1)
    timestamps = [step * (i + 1) for i in range(n_frames)]
    return timestamps, f"fixed-interval/{n_frames}"


def ydlp_download_video(url: str, dest_dir: Path, *, format_pref: str = "worst[height<=480]") -> Path | None:
    """Download a video at low resolution for frame extraction. Returns the path or None."""
    from yt_dlp import YoutubeDL  # type: ignore

    out_tmpl = str(dest_dir / "%(id)s.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": format_pref,
        "outtmpl": out_tmpl,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        # Resolve actual file path
        candidates = list(dest_dir.glob(f"{info['id']}.*"))
        videos = [p for p in candidates if p.suffix.lower() not in (".json", ".description")]
        return videos[0] if videos else None
    except Exception as e:  # noqa: BLE001
        log.warning("yt-dlp download failed: %s", type(e).__name__)
        return None


def ffmpeg_extract_frame(video: Path, timestamp_s: float, dest: Path) -> bool:
    """Extract a single JPEG frame at timestamp_s, downscaled per CONFIG."""
    width = CONFIG.limits.youtube_frame_resize_width
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{timestamp_s:.2f}",
        "-i", str(video),
        "-vframes", "1",
        "-q:v", "3",
        "-vf", f"scale={width}:-1",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and dest.exists()


def fetch_visual_local(
    url: str, video_id: str, metadata: dict, transcript: dict | None,
) -> dict | None:
    """T3-local: download video, sample frames, gemma4 vision per frame, aggregate."""
    from core import ollama_client  # noqa: WPS433  late import — config must be ready

    if not ollama_client.is_reachable():
        log.warning("Ollama not reachable — skipping T3 visual")
        return None

    duration = float(metadata.get("duration_s") or 0)
    max_dur = CONFIG.limits.youtube_max_duration_s
    if duration > max_dur:
        log.warning("video duration %.0fs > %ds (CONFIG.limits.youtube_max_duration_s) — skipping T3",
                    duration, max_dur)
        return None
    if duration <= 0:
        log.warning("no duration metadata — skipping T3")
        return None

    timestamps, strategy = pick_frame_timestamps(metadata)
    if not timestamps:
        return None
    log.info("T3-local: %d frames, strategy=%s", len(timestamps), strategy)

    with tempfile.TemporaryDirectory(prefix=f"yt-t3-{video_id}-") as tmp_str:
        tmp = Path(tmp_str)
        log.info("  downloading video at low-res …")
        t0 = time.time()
        video_path = ydlp_download_video(url, tmp)
        if not video_path or not video_path.exists():
            log.warning("  no video file downloaded — skipping T3")
            return None
        log.info("  downloaded %s (%.1f MB) in %.1fs",
                 video_path.name, video_path.stat().st_size / 1e6, time.time() - t0)

        per_frame: list[dict] = []
        for i, ts in enumerate(timestamps):
            frame_path = tmp / f"frame-{i:03d}.jpg"
            ok = ffmpeg_extract_frame(video_path, ts, frame_path)
            if not ok:
                log.warning("  frame extract failed at %.1fs", ts)
                continue
            try:
                img_b64 = base64.b64encode(frame_path.read_bytes()).decode()
                t1 = time.time()
                content, _stats = ollama_client.chat_vision(
                    FRAME_PROMPT,
                    model=CONFIG.models.vision_model,
                    image_b64=img_b64,
                    timeout=float(CONFIG.limits.youtube_vision_timeout_s),
                )
                summary = content.strip()
                informative = not summary.upper().startswith("UNINFORMATIVE")
                per_frame.append({
                    "timestamp_s": round(ts, 2),
                    "timestamp_label": _ts_to_label(ts),
                    "informative": informative,
                    "summary": summary,
                    "duration_s": round(time.time() - t1, 2),
                })
                log.info("  frame %d/%d @ %s: %s",
                         i + 1, len(timestamps), _ts_to_label(ts),
                         "skip (uninformative)" if not informative else summary[:80])
            except Exception as e:  # noqa: BLE001
                log.warning("  vision call failed at %.1fs: %s", ts, type(e).__name__)
                continue

        # Aggregate (reuses the local vision-capable model in text mode —
        # gemma4 / qwen2.5-vl handle both, no need for a second model field).
        agg_model = CONFIG.models.vision_model
        log.info("  aggregating with %s …", agg_model)
        agg_prompt = _build_aggregate_prompt(metadata, transcript, per_frame)
        try:
            t1 = time.time()
            aggregate = ollama_client.chat(
                agg_prompt,
                model=agg_model,
                temperature=0.2,
                timeout=float(CONFIG.limits.youtube_aggregate_timeout_s),
            )
            agg_duration = round(time.time() - t1, 2)
        except Exception as e:  # noqa: BLE001
            log.warning("aggregate call failed: %s", type(e).__name__)
            aggregate = ""
            agg_duration = 0

        return {
            "provider": "local",
            "model": f"{CONFIG.models.vision_model}@ollama",
            "strategy": strategy,
            "frames_planned": len(timestamps),
            "frames_analyzed": len(per_frame),
            "frames_informative": sum(1 for f in per_frame if f["informative"]),
            "per_frame": per_frame,
            "aggregate": aggregate,
            "aggregate_duration_s": agg_duration,
        }


def _build_aggregate_prompt(metadata: dict, transcript: dict | None, frames: list[dict]) -> str:
    transcript_block = (transcript or {}).get("plain") or "(no subtitles available — rely on visual track)"
    # Context-window safety: keep transcript + frames within ~16k tokens
    max_transcript_chars = 12000
    if len(transcript_block) > max_transcript_chars:
        transcript_block = transcript_block[:max_transcript_chars] + "\n[…truncated…]"

    informative = [f for f in frames if f["informative"]]
    if informative:
        frames_block = "\n".join(f"[{f['timestamp_label']}] {f['summary']}" for f in informative)
    else:
        frames_block = "(no informative frames captured)"

    duration_min = int((metadata.get("duration_s") or 0) // 60)
    return AGGREGATE_PROMPT_TEMPLATE.format(
        title=metadata.get("title") or "(untitled)",
        channel=metadata.get("channel") or "(unknown)",
        duration_min=duration_min,
        upload_date=metadata.get("upload_date") or "(unknown)",
        transcript_block=transcript_block,
        frames_block=frames_block,
    )


# ── Slugging + write ─────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


@dataclass
class Sidecar:
    url: str
    video_id: str
    ingested_at: str
    tier: int
    input_source: str
    user_note: str | None
    metadata: dict
    transcript: dict | None = None
    comments: list[dict] = field(default_factory=list)
    visual: dict | None = None  # T3 analysis (local or cloud)


def slim_metadata(info: dict) -> dict:
    """Project the fields we care about out of yt-dlp's raw info dict."""
    return {
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "duration_s": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "description": info.get("description"),
        "tags": info.get("tags") or [],
        "categories": info.get("categories") or [],
        "chapters": info.get("chapters") or [],
        "thumbnail": info.get("thumbnail"),
        "language": info.get("language"),
    }


def render_markdown(side: Sidecar) -> str:
    m = side.metadata
    front = {
        "type": "transcript" if side.transcript else "note",
        "source": "youtube",
        "video_id": side.video_id,
        "url": side.url,
        "title": m.get("title"),
        "channel": m.get("channel"),
        "duration_s": m.get("duration_s"),
        "upload_date": m.get("upload_date"),
        "tags": list(dict.fromkeys((m.get("tags") or []) + ["youtube"])),
        "ingested_at": side.ingested_at,
        "tier": side.tier,
        "input_source": side.input_source,
        "transcript_language": (side.transcript or {}).get("language"),
        "comment_sample_size": len(side.comments),
        "visual_model": (side.visual or {}).get("model"),
        "visual_frames": (side.visual or {}).get("frames_analyzed"),
    }
    if side.user_note:
        front["user_note"] = side.user_note
    fm = yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip()

    parts: list[str] = [f"---\n{fm}\n---", "", f"# {m.get('title') or side.video_id}", ""]
    parts.append(f"<https://www.youtube.com/watch?v={side.video_id}>  ")
    parts.append(
        f"_{m.get('channel') or 'unknown channel'} · "
        f"{(m.get('duration_s') or 0) // 60} min · "
        f"uploaded {m.get('upload_date') or '—'}_"
    )
    parts.append("")

    if side.user_note:
        parts.append(f"> [!note] User note\n> {side.user_note}\n")

    desc = (m.get("description") or "").strip()
    if desc:
        parts.append("## Description\n")
        parts.append(desc)
        parts.append("")

    chapters = m.get("chapters") or []
    if chapters:
        parts.append("## Chapters\n")
        for ch in chapters:
            start = int(ch.get("start_time") or 0)
            mm, ss = divmod(start, 60)
            parts.append(f"- `{mm:02d}:{ss:02d}` {ch.get('title')}")
        parts.append("")

    if side.transcript:
        parts.append(f"## Transcript ({side.transcript['language']}, "
                     f"{'auto' if side.transcript.get('is_generated') else 'manual'})\n")
        parts.append(side.transcript["plain"])
        parts.append("")

    if side.visual and side.visual.get("aggregate"):
        v = side.visual
        parts.append(f"## Visual analysis ({v.get('model')}, {v.get('frames_informative', 0)}/{v.get('frames_analyzed', 0)} informative frames)\n")
        parts.append(v["aggregate"].strip())
        parts.append("")
        parts.append("<details><summary>Per-frame log</summary>\n")
        for f in v.get("per_frame", []):
            tag = "" if f.get("informative") else " _(uninformative)_"
            parts.append(f"- `[{f.get('timestamp_label')}]`{tag} {f.get('summary')}")
        parts.append("\n</details>")
        parts.append("")

    if side.comments:
        parts.append(f"## Top comments ({len(side.comments)})\n")
        for c in side.comments:
            badge = " 👤 creator" if c.get("is_creator") else ""
            likes = c.get("like_count") or 0
            text = (c.get("text") or "").strip().replace("\n", " ")
            parts.append(f"- **{c.get('author') or 'anon'}**{badge} (▲{likes}): {text}")
        parts.append("")

    return "\n".join(parts) + "\n"


def write_sidecar(side: Sidecar, *, out_dir: Path) -> Path:
    """Write the per-video markdown — single source of truth.

    Earlier revisions also wrote a parallel `.json` sidecar with the raw
    structured payload. Dropped 2026-05-03: compile.py only reads `.md`,
    timestamps live as `[mm:ss]` text anchors inside the markdown body,
    and yt-dlp / transcript-api are deterministic if anyone ever needs
    to re-derive the structured shape.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    channel_slug = slugify(side.metadata.get("channel") or "unknown")
    title_slug = slugify(side.metadata.get("title") or side.video_id, max_len=50)
    base = f"{channel_slug}--{title_slug}--{side.video_id}"
    md_path = out_dir / f"{base}.md"
    md_path.write_text(render_markdown(side), encoding="utf-8")
    return md_path


# ── Per-video pipeline ───────────────────────────────────────────────

def ingest_one(
    url: str,
    *,
    tier: int,
    input_source: str,
    user_note: str | None,
    out_dir: Path,
    dry_run: bool,
    skip_existing: bool,
) -> dict | None:
    video_id = extract_video_id(url)
    if not video_id:
        log.warning("could not extract video id from %s", url)
        return None

    if skip_existing and any(out_dir.glob(f"*--{video_id}.md")):
        log.info("skip existing %s", video_id)
        return {"video_id": video_id, "status": "skipped"}

    log.info("[T%d] ingest %s …", tier, video_id)
    info = fetch_metadata(url, with_comments=tier >= 2)
    metadata = slim_metadata(info)

    transcript = fetch_transcript(video_id) if tier >= 1 else None
    comments = slim_comments(info.get("comments")) if tier >= 2 else []
    visual = None
    if tier >= 3 and not dry_run:
        visual = fetch_visual_local(url, video_id, metadata, transcript)

    side = Sidecar(
        url=url,
        video_id=video_id,
        ingested_at=now_iso(),
        tier=tier,
        input_source=input_source,
        user_note=user_note,
        metadata=metadata,
        transcript=transcript,
        comments=comments,
        visual=visual,
    )

    if dry_run:
        log.info(
            "  DRY: %s — %s · transcript=%s · comments=%d · visual=%s",
            metadata.get("title"),
            metadata.get("channel"),
            "yes" if transcript else "no",
            len(comments),
            "yes" if visual else ("would-run" if tier >= 3 else "no"),
        )
        return {"video_id": video_id, "status": "dry"}

    md_path = write_sidecar(side, out_dir=out_dir)
    log.info("  wrote %s", md_path.relative_to(out_dir.parent.parent.parent) if str(md_path).startswith(str(out_dir.parent.parent.parent)) else md_path)
    return {"video_id": video_id, "status": "written", "path": str(md_path)}


# ── CLI ──────────────────────────────────────────────────────────────

def _ingest_items(
    items: list[InboxItem],
    *,
    default_tier: int,
    input_source: str,
    effective_limit: int | None,
    dry_run: bool,
    skip_existing: bool,
    out_dir: Path,
) -> dict:
    """Expand playlists, cap by limit, ingest each video. Shared by `main()`
    (CLI) and `drain_inbox()` (Collector path).

    Returns a result dict: ``{"written", "skipped", "failed", "results"}``.
    """
    urls_to_process: list[tuple[str, str | None, int]] = []
    for it in items:
        tier = it.tier_override if it.tier_override is not None else default_tier
        if is_playlist_url(it.url):
            for u in expand_playlist(it.url, limit=effective_limit):
                urls_to_process.append((u, it.note, tier))
        else:
            urls_to_process.append((it.url, it.note, tier))

    if effective_limit and len(urls_to_process) > effective_limit:
        urls_to_process = urls_to_process[:effective_limit]

    log.info("ingesting %d videos at tier %d", len(urls_to_process), default_tier)
    results: list[dict] = []
    for u, note, tier in urls_to_process:
        try:
            r = ingest_one(
                u,
                tier=tier,
                input_source=input_source,
                user_note=note,
                out_dir=out_dir,
                dry_run=dry_run,
                skip_existing=skip_existing,
            )
            if r:
                results.append(r)
        except KeyboardInterrupt:
            log.warning("interrupted")
            break
        except Exception as e:  # noqa: BLE001
            log.exception("failed on %s: %s", u, e)
            results.append({"url": u, "status": "failed", "error": str(e)})

    written = sum(1 for r in results if r.get("status") == "written")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    failed = sum(1 for r in results if r.get("status") == "failed")
    log.info("done — %d written · %d skipped · %d failed", written, skipped, failed)
    return {"written": written, "skipped": skipped, "failed": failed, "results": results}


def drain_inbox(
    inbox_path: Path = INBOX_FILE,
    *,
    tier: int = 1,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Process a YouTube inbox markdown file (the Collector / piggyback path).

    Returns ``{"processed", "written", "report_paths", "message"}``. A
    missing inbox file is a clean no-op, not an error.
    """
    if not inbox_path.exists():
        return {"processed": 0, "written": 0, "report_paths": [],
                "message": f"no inbox file at {inbox_path}"}

    items = parse_inbox(inbox_path.read_text(encoding="utf-8"))
    if not items:
        return {"processed": 0, "written": 0, "report_paths": [],
                "message": f"inbox {inbox_path.name} is empty"}

    # Inbox limit defaults to CONFIG.piggybacks.scan_youtube.max_per_run so a
    # runaway inbox doesn't burn a whole day. (Config key stays scan_youtube —
    # see config.example.yaml; the Collector SPEC.name is "youtube".)
    if limit is None:
        pb = CONFIG.piggybacks.get("scan_youtube")
        limit = pb.max_per_run if pb else None

    result = _ingest_items(
        items,
        default_tier=tier,
        input_source="inbox",
        effective_limit=limit,
        dry_run=dry_run,
        skip_existing=True,
        out_dir=REPORT_DIR,
    )
    report_paths = [
        Path(r["path"]) for r in result["results"] if r.get("status") == "written" and r.get("path")
    ]
    return {
        "processed": len(result["results"]),
        "written": result["written"],
        "report_paths": report_paths,
        "message": (
            f"{result['written']} written · {result['skipped']} skipped · {result['failed']} failed"
        ),
    }


# ── Collector wrapper ───────────────────────────────────────────────


@register
class YoutubeCollector:
    """YouTube ingest — Collector Protocol wrapper.

    The Collector path is the **inbox-drain** mode: `run()` processes
    `raw/inbox/youtube.md` (a markdown URL list, optionally with inline
    `tier: N` directives). The rich per-URL CLI (`--url`, `--tier`,
    `--no-skip`, playlist expansion) stays on the direct script /
    `wiki ingest-youtube` wrapper — same split as calendar's `--year`
    and browser's `--source`.

    `piggyback_default=False`: youtube ingest is operator-paced (you drop
    URLs into the inbox, then drain when ready), not a blind daily sweep.
    """

    SPEC = CollectorSpec(
        name="youtube",
        output_subfolder="raw/notes/youtube",
        piggyback_default=False,
        piggyback_cooldown_hours=24,
        supports_incremental=False,  # skip-existing dedup is always on; no delta concept
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        """True iff the YouTube inbox file exists (that's the Collector path's input)."""
        return INBOX_FILE.is_file()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        if not self.is_configured():
            return RunResult(message=f"No YouTube inbox at {INBOX_FILE} — drop URLs there or use `wiki ingest-youtube --url`")

        result = drain_inbox(INBOX_FILE, dry_run=dry_run)
        return RunResult(
            files_written=tuple(result["report_paths"]),
            files_skipped=result["processed"] - result["written"],
            message=result["message"],
        )


# ── Direct CLI entry (backward-compat) ──────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(prog="scan-youtube")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="single video or playlist URL")
    src.add_argument("--inbox", help="path to a markdown file with YouTube URLs")
    parser.add_argument("--tier", type=int, choices=[0, 1, 2, 3], default=1)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap playlist/inbox expansion (default: CONFIG.piggybacks.scan_youtube.max_per_run for --inbox, unlimited for --url)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true", help="re-ingest videos already in raw/notes/youtube/")
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args()

    items: list[InboxItem] = []
    if args.url:
        items = [InboxItem(url=args.url)]
        input_source = "cli"
        # CLI --url paths default to no limit (user explicitly named one URL).
        effective_limit = args.limit
    else:
        path = Path(args.inbox).expanduser()
        if not path.exists():
            log.error("inbox file not found: %s", path)
            return 2
        items = parse_inbox(path.read_text(encoding="utf-8"))
        input_source = "inbox"
        log.info("inbox: %d items", len(items))
        # Inbox piggyback path defaults to CONFIG.piggybacks.scan_youtube.max_per_run
        # (mirrors scan-screenshots convention) so a runaway inbox doesn't burn a whole day.
        if args.limit is not None:
            effective_limit = args.limit
        else:
            pb = CONFIG.piggybacks.get("scan_youtube")
            effective_limit = (pb.max_per_run if pb else None)

    result = _ingest_items(
        items,
        default_tier=args.tier,
        input_source=input_source,
        effective_limit=effective_limit,
        dry_run=args.dry_run,
        skip_existing=not args.no_skip,
        out_dir=args.out,
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
