"""Voice intake — folder-watching collector for dictated text + audio notes.

Operator dictates with any tool (OpenWhispr / FluidVoice / macOS dictation
/ Voice Memos), the tool writes a transcript (.txt / .md) or audio file
(.m4a / .mp4 / .mp3 / .wav / .flac / .ogg / .aac) into the configured
`personal.voice_inbox` directory. This collector picks them up, writes a
frontmatter-stamped copy into `raw/voice/`, and archives the source under
`raw/inbox-mobile/voice/` (vault-internal audit zone, M022 two-zone intake).

Audio files are transcribed locally via whisper.cpp (M026, 2026-05-28).
Operator pre-reqs: `brew install whisper-cpp` plus a ggml model file
(e.g. `~/whisper-models/ggml-base.bin`), pointed at by the config keys
`personal.voice_transcribe_model` + friends. Without setup, audio files
are left in the inbox and surface as `errors[]` — text dictation keeps
working regardless.

Substrate-agnostic on the capture side, opinionated on the storage side
— same pattern as jamie / gmeet. See `.ytstack/backlog/voice-intake.md`
for the design rationale + dictation-tool landscape.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from core import daily_capture, ollama_client
from core.config import CONFIG, TIMEZONE
from core.paths import RAW_DIR
from core.prompts import render
from core.utils import slugify

log = logging.getLogger(__name__)

OUTPUT_DIR = RAW_DIR / "voice"
MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "voice"
TEXT_SUFFIXES = (".txt", ".md")
# Audio formats accepted by the inbox. whisper-cli natively reads
# mp3 / wav / flac / ogg; m4a / mp4 / aac go through ffmpeg first
# (16 kHz mono PCM s16 — whisper's preferred input shape).
AUDIO_SUFFIXES = (".m4a", ".mp4", ".mp3", ".wav", ".flac", ".ogg", ".aac")
ACCEPTED_SUFFIXES = TEXT_SUFFIXES + AUDIO_SUFFIXES
_WHISPER_NATIVE_SUFFIXES = (".mp3", ".wav", ".flac", ".ogg")
MAX_SLUG_WORDS = 6
PUNCTUATE_TIMEOUT_S = 30.0
TRANSCRIBE_TIMEOUT_S = 600.0
FFMPEG_TIMEOUT_S = 120.0


def _punctuate(raw_transcript: str) -> str | None:
    """Send a voice transcript through the local classify_model to add
    punctuation + German-noun-case. Returns the cleaned text, or None on
    any failure (caller falls back to raw). Skip-and-fallback rather than
    raise: voice ingest must never fail because of an Ollama hiccup.
    """
    try:
        prompt = render("voice_punctuate", raw_transcript=raw_transcript)
        cleaned = ollama_client.chat(
            prompt,
            model=CONFIG.models.classify_model,
            temperature=0.0,
            timeout=PUNCTUATE_TIMEOUT_S,
        )
        cleaned = cleaned.strip()
        # Sanity: if model returned empty or absurdly longer text (>3× source),
        # assume it hallucinated commentary — fall back to raw.
        if not cleaned:
            log.warning("voice punctuation returned empty, falling back to raw")
            return None
        if len(cleaned) > 3 * max(len(raw_transcript), 40):
            log.warning(
                "voice punctuation returned %d chars from %d-char source — likely hallucination, falling back to raw",
                len(cleaned), len(raw_transcript),
            )
            return None
        return cleaned
    except Exception as exc:  # noqa: BLE001
        log.warning("voice punctuation failed (%s) — falling back to raw", exc)
        return None


def _inbox_path() -> Path | None:
    raw = (CONFIG.personal.voice_inbox or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _resolve_binary(configured: str, fallback_name: str) -> str | None:
    """Resolve a binary path: explicit config value wins, else PATH lookup.

    Returns the resolved path string, or None if neither yields a callable
    binary (the caller logs a warning + falls back to skip).
    """
    configured = (configured or "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
        log.warning("configured %s path %s does not exist — falling back to $PATH", fallback_name, p)
    found = shutil.which(fallback_name)
    return found  # None if not on PATH


def _transcribe_audio(src: Path) -> str | None:
    """Run whisper.cpp on an audio file and return the cleaned transcript.

    Pipeline:
      1. Resolve model path from `personal.voice_transcribe_model`. Empty
         or missing → log + return None (file stays in inbox).
      2. Resolve whisper-cli binary (explicit override → $PATH lookup).
      3. For non-native formats (m4a / mp4 / aac), shell out to ffmpeg
         first to produce a 16 kHz mono PCM s16 WAV — whisper's preferred
         input shape. Native formats (mp3 / wav / flac / ogg) skip this.
      4. Invoke whisper-cli with `-nt -np` so stdout carries just the
         transcript text. Stderr (Metal/CPU init noise + a duplicate
         transcript echo) is discarded to DEBUG.

    Any step failing returns None — the caller leaves the source in the
    inbox so the operator can retry once setup is healthy. We never
    raise from here: voice ingest must not break the collector loop.
    """
    model_raw = (CONFIG.personal.voice_transcribe_model or "").strip()
    if not model_raw:
        log.warning(
            "audio file %s in voice_inbox but personal.voice_transcribe_model is empty — leaving in inbox",
            src.name,
        )
        return None
    model_path = Path(model_raw).expanduser()
    if not model_path.is_file():
        log.warning(
            "voice_transcribe_model %s does not exist — leaving audio file %s in inbox",
            model_path, src.name,
        )
        return None

    whisper = _resolve_binary(CONFIG.personal.voice_transcribe_binary, "whisper-cli")
    if not whisper:
        log.warning(
            "whisper-cli not on $PATH (install: brew install whisper-cpp) — leaving audio file %s in inbox",
            src.name,
        )
        return None

    suffix = src.suffix.lower()
    language = (CONFIG.personal.voice_transcribe_language or "auto").strip() or "auto"
    threads = max(1, int(CONFIG.personal.voice_transcribe_threads))

    with tempfile.TemporaryDirectory(prefix="voice-transcribe-") as tmp:
        if suffix in _WHISPER_NATIVE_SUFFIXES:
            audio_path = src
        else:
            ffmpeg = _resolve_binary(CONFIG.personal.voice_transcribe_ffmpeg, "ffmpeg")
            if not ffmpeg:
                log.warning(
                    "ffmpeg not on $PATH (needed for %s; native whisper formats are mp3/wav/flac/ogg) — leaving %s in inbox",
                    suffix, src.name,
                )
                return None
            audio_path = Path(tmp) / "audio.wav"
            try:
                subprocess.run(
                    [
                        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(src),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                        str(audio_path),
                    ],
                    check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                log.warning("ffmpeg timed out after %ds converting %s — leaving in inbox",
                            int(FFMPEG_TIMEOUT_S), src.name)
                return None
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
                log.warning("ffmpeg failed (%s) on %s: %s — leaving in inbox",
                            exc.returncode, src.name, stderr[:200])
                return None

        try:
            result = subprocess.run(
                [
                    whisper,
                    "-m", str(model_path),
                    "-l", language,
                    "-t", str(threads),
                    "-nt", "-np",
                    "-f", str(audio_path),
                ],
                check=True, capture_output=True, text=True, timeout=TRANSCRIBE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            log.warning("whisper-cli timed out after %ds on %s — leaving in inbox",
                        int(TRANSCRIBE_TIMEOUT_S), src.name)
            return None
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            log.warning("whisper-cli failed (%s) on %s: %s — leaving in inbox",
                        exc.returncode, src.name, stderr[-200:])
            return None

    text = (result.stdout or "").strip()
    if not text:
        log.warning("whisper-cli returned empty transcript for %s — leaving in inbox", src.name)
        return None
    log.info("transcribed %s (%d chars, lang=%s, model=%s)",
             src.name, len(text), language, model_path.name)
    return text


def _build_filename(captured_at: datetime, content: str) -> str:
    stamp = captured_at.strftime("%Y-%m-%d-%H%M")
    first_words = " ".join(content.split()[:MAX_SLUG_WORDS])
    slug = slugify(first_words) or "note"
    return f"voice-{stamp}-{slug}.md"


def _build_frontmatter(
    captured_at: datetime,
    source: Path,
    raw_transcript: str | None = None,
) -> str:
    """Frontmatter for a raw/voice/*.md note.

    When `raw_transcript` is provided, the punctuation pre-process ran and
    the body holds the cleaned version — we preserve the verbatim raw text
    under `raw_transcript:` for audit. When None, body == raw and the key
    is omitted.
    """
    lines = [
        "---",
        "type: voice-note",
        "origin: voice-intake",
        f"captured_at: {captured_at.isoformat()}",
        f"source: {source.name}",
        "tags: [voice]",
    ]
    if raw_transcript is not None:
        # YAML block-literal preserves newlines + non-ASCII verbatim.
        lines.append("raw_transcript: |")
        for raw_line in raw_transcript.splitlines() or [raw_transcript]:
            lines.append(f"  {raw_line}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


def _scan_inbox(inbox: Path) -> list[Path]:
    """List inbox files eligible for ingest. Skips dot-files and anything
    whose suffix isn't in ACCEPTED_SUFFIXES (text: .txt / .md; audio:
    .m4a / .mp4 / .mp3 / .wav / .flac / .ogg / .aac)."""
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


def _append_daily_rollup(captured_at: datetime, content: str, out_path: Path) -> None:
    """Append a voice-intake one-liner to daily/<date>/voice.md.

    The daily/-rollup substrate (`.ytstack/AD-HOC-daily-as-rollup-PLAN.md`)
    surfaces one line per voice note: time, first few words, link back to
    the canonical raw/voice/ file. Failures are swallowed — the rollup is
    side-effect, never break the primary write.
    """
    date_iso = captured_at.strftime("%Y-%m-%d")
    time_label = captured_at.strftime("%H:%M")
    first_line = content.splitlines()[0].strip() if content else "(empty)"
    if len(first_line) > 80:
        first_line = first_line[:77].rstrip() + "…"
    line = f"- **{time_label}** · {first_line} → [[{out_path.stem}]]"
    try:
        daily_capture.append(date_iso, "voice", line)
    except Exception:  # noqa: BLE001
        log.exception("daily-rollup append failed for voice note %s", out_path.name)


@register
class VoiceCollector:
    """Voice intake — inbox-watching transcript ingester.

    Reads any `*.txt` / `*.md` from `personal.voice_inbox`, writes a
    frontmatter-stamped copy to `raw/voice/`, then archives the source
    under `raw/inbox-mobile/voice/` (vault-internal). No state file —
    the archive move is the dedup mechanism.
    """

    SPEC = CollectorSpec(
        name="voice",
        output_subfolder="raw/voice",
        piggyback_default=True,
        piggyback_cooldown_hours=1,
        supports_incremental=False,
        supports_account_loop=False,
    )

    def is_configured(self) -> bool:
        inbox = _inbox_path()
        return inbox is not None and inbox.exists()

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        inbox = _inbox_path()
        if inbox is None:
            return RunResult(message="voice_inbox not configured (personal.voice_inbox is empty)")
        if not inbox.exists():
            return RunResult(message=f"voice_inbox not found: {inbox}")

        tz = ZoneInfo(TIMEZONE)
        sources = _scan_inbox(inbox)
        if not sources:
            return RunResult(message=f"no new voice notes in {inbox}")

        if dry_run:
            return RunResult(
                files_skipped=len(sources),
                message=f"[dry-run] would ingest {len(sources)} voice note(s) from {inbox}",
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        MOBILE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        punctuate_enabled = CONFIG.features.voice_punctuate

        written: list[Path] = []
        errors: list[str] = []
        for src in sources:
            is_audio = src.suffix.lower() in AUDIO_SUFFIXES
            if is_audio:
                raw = _transcribe_audio(src)
                if raw is None:
                    # Transcription disabled/failed — leave the file in
                    # the inbox so a re-run picks it up once setup is
                    # healthy (model installed, binary on PATH, etc.).
                    errors.append(f"{src.name}: transcription unavailable, left in inbox")
                    continue
                raw = raw.strip()
            else:
                try:
                    raw = src.read_text(encoding="utf-8").strip()
                except (UnicodeDecodeError, OSError) as exc:
                    errors.append(f"{src.name}: read failed ({exc})")
                    continue
            if not raw:
                errors.append(f"{src.name}: empty content, archived without ingest")
                shutil.move(str(src), str(MOBILE_ARCHIVE_DIR / src.name))
                continue

            # Punctuation pre-process. Cleaned body + raw preserved in FM.
            # Fallback (Ollama down, hallucination guard tripped, feature
            # off): body = raw, no raw_transcript frontmatter key.
            cleaned: str | None = None
            if punctuate_enabled:
                cleaned = _punctuate(raw)
            body = cleaned if cleaned is not None else raw

            captured_at = datetime.fromtimestamp(src.stat().st_mtime, tz=tz)
            out_name = _build_filename(captured_at, body)
            out_path = OUTPUT_DIR / out_name
            # Same-minute slug collision: append seconds.
            if out_path.exists():
                out_path = OUTPUT_DIR / out_name.replace(
                    ".md", f"-{captured_at.strftime('%S')}.md"
                )

            frontmatter = _build_frontmatter(
                captured_at,
                src,
                raw_transcript=raw if cleaned is not None else None,
            )
            out_path.write_text(frontmatter + body + "\n", encoding="utf-8")
            written.append(out_path)

            # Mirror a one-liner into daily/<date>/voice.md so the day's
            # voice-intake activity surfaces in the rollup substrate.
            _append_daily_rollup(captured_at, body, out_path)

            try:
                # If archive already has a same-name file (re-run after manual
                # restore), suffix the archive copy with mtime to avoid clobber.
                dest = MOBILE_ARCHIVE_DIR / src.name
                if dest.exists():
                    dest = MOBILE_ARCHIVE_DIR / f"{src.stem}-{int(src.stat().st_mtime)}{src.suffix}"
                shutil.move(str(src), str(dest))
            except OSError as exc:
                errors.append(f"{src.name}: archive failed ({exc})")

        return RunResult(
            files_written=tuple(written),
            files_skipped=len(sources) - len(written),
            message=f"{len(written)} voice note(s) ingested from {inbox}",
            errors=tuple(errors),
        )
