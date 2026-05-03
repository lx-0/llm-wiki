"""
Scan YouTube URLs (single video, playlist, or inbox-list) and write tiered
metadata + transcript + comments into raw/notes/youtube/.

First-aufschlag scope: Tier 0 (yt-dlp metadata), Tier 1 (subtitles via
youtube-transcript-api with yt-dlp fallback), Tier 2 (top comments via
yt-dlp). All free, no LLM. Tier 3 (gemma4 frame-sampling / Gemini cloud)
is a follow-up — see .ytstack/backlog/youtube-intake.md.

Usage:
    uv run python scripts/scan-youtube.py --url URL [--tier {0,1,2}] [--limit N]
    uv run python scripts/scan-youtube.py --inbox PATH [--tier {0,1,2}] [--limit N]
    uv run python scripts/scan-youtube.py --url URL --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from config import RAW_DIR, now_iso

# yt-dlp + youtube-transcript-api are imported lazily so --help works
# without the deps installed.

REPORT_DIR = RAW_DIR / "notes" / "youtube"

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

    if side.comments:
        parts.append(f"## Top comments ({len(side.comments)})\n")
        for c in side.comments:
            badge = " 👤 creator" if c.get("is_creator") else ""
            likes = c.get("like_count") or 0
            text = (c.get("text") or "").strip().replace("\n", " ")
            parts.append(f"- **{c.get('author') or 'anon'}**{badge} (▲{likes}): {text}")
        parts.append("")

    return "\n".join(parts) + "\n"


def write_sidecar(side: Sidecar, *, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    channel_slug = slugify(side.metadata.get("channel") or "unknown")
    title_slug = slugify(side.metadata.get("title") or side.video_id, max_len=50)
    base = f"{channel_slug}--{title_slug}--{side.video_id}"
    md_path = out_dir / f"{base}.md"
    json_path = out_dir / f"{base}.json"
    md_path.write_text(render_markdown(side), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "url": side.url,
                "video_id": side.video_id,
                "ingested_at": side.ingested_at,
                "tier": side.tier,
                "input_source": side.input_source,
                "user_note": side.user_note,
                "metadata": side.metadata,
                "transcript": side.transcript,
                "comments": side.comments,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return md_path, json_path


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

    if skip_existing and any(out_dir.glob(f"*--{video_id}.json")):
        log.info("skip existing %s", video_id)
        return {"video_id": video_id, "status": "skipped"}

    log.info("[T%d] ingest %s …", tier, video_id)
    info = fetch_metadata(url, with_comments=tier >= 2)
    metadata = slim_metadata(info)

    transcript = fetch_transcript(video_id) if tier >= 1 else None
    comments = slim_comments(info.get("comments")) if tier >= 2 else []

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
    )

    if dry_run:
        log.info(
            "  DRY: %s — %s · transcript=%s · comments=%d",
            metadata.get("title"),
            metadata.get("channel"),
            "yes" if transcript else "no",
            len(comments),
        )
        return {"video_id": video_id, "status": "dry"}

    md_path, _ = write_sidecar(side, out_dir=out_dir)
    log.info("  wrote %s", md_path.relative_to(out_dir.parent.parent.parent) if str(md_path).startswith(str(out_dir.parent.parent.parent)) else md_path)
    return {"video_id": video_id, "status": "written", "path": str(md_path)}


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(prog="scan-youtube")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="single video or playlist URL")
    src.add_argument("--inbox", help="path to a markdown file with YouTube URLs")
    parser.add_argument("--tier", type=int, choices=[0, 1, 2], default=1)
    parser.add_argument("--limit", type=int, default=None, help="cap playlist expansion")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true", help="re-ingest videos already in raw/notes/youtube/")
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args()

    items: list[InboxItem] = []
    if args.url:
        items = [InboxItem(url=args.url)]
        input_source = "cli"
    else:
        path = Path(args.inbox).expanduser()
        if not path.exists():
            log.error("inbox file not found: %s", path)
            return 2
        items = parse_inbox(path.read_text(encoding="utf-8"))
        input_source = "inbox"
        log.info("inbox: %d items", len(items))

    urls_to_process: list[tuple[str, str | None, int]] = []
    for it in items:
        tier = it.tier_override if it.tier_override is not None else args.tier
        if is_playlist_url(it.url):
            for u in expand_playlist(it.url, limit=args.limit):
                urls_to_process.append((u, it.note, tier))
        else:
            urls_to_process.append((it.url, it.note, tier))

    if args.limit and len(urls_to_process) > args.limit:
        urls_to_process = urls_to_process[: args.limit]

    log.info("ingesting %d videos at tier %d", len(urls_to_process), args.tier)
    results = []
    for u, note, tier in urls_to_process:
        try:
            r = ingest_one(
                u,
                tier=tier,
                input_source=input_source,
                user_note=note,
                out_dir=args.out,
                dry_run=args.dry_run,
                skip_existing=not args.no_skip,
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
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
