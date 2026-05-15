"""Voice intake — folder-watching collector for dictated text notes.

Operator dictates with any tool (OpenWhispr / FluidVoice / macOS
dictation), the tool writes the transcript as a .txt or .md into the
configured `personal.voice_inbox` directory. This collector picks them
up, writes a frontmatter-stamped copy into `raw/voice/`, and archives
the source under `<voice_inbox>/.processed/`.

Substrate-agnostic on the capture side, opinionated on the storage side
— same pattern as jamie / gmeet. See `.ytstack/backlog/voice-intake.md`
for the design rationale + dictation-tool landscape.
"""

from __future__ import annotations

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import Collector, CollectorSpec, RunResult, register
from core.config import CONFIG, TIMEZONE
from core.paths import RAW_DIR
from core.utils import slugify

log = logging.getLogger(__name__)

OUTPUT_DIR = RAW_DIR / "voice"
ARCHIVE_SUBDIR = ".processed"
ACCEPTED_SUFFIXES = (".txt", ".md")
MAX_SLUG_WORDS = 6


def _inbox_path() -> Path | None:
    raw = (CONFIG.personal.voice_inbox or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _build_filename(captured_at: datetime, content: str) -> str:
    stamp = captured_at.strftime("%Y-%m-%d-%H%M")
    first_words = " ".join(content.split()[:MAX_SLUG_WORDS])
    slug = slugify(first_words) or "note"
    return f"voice-{stamp}-{slug}.md"


def _build_frontmatter(captured_at: datetime, source: Path) -> str:
    return (
        "---\n"
        "type: voice-note\n"
        "origin: voice-intake\n"
        f"captured_at: {captured_at.isoformat()}\n"
        f"source: {source.name}\n"
        "tags: [voice]\n"
        "---\n\n"
    )


def _scan_inbox(inbox: Path) -> list[Path]:
    """List inbox files eligible for ingest. Skips dot-files, .processed/,
    and anything whose suffix isn't .txt / .md."""
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


@register
class VoiceCollector:
    """Voice intake — inbox-watching transcript ingester.

    Reads any `*.txt` / `*.md` from `personal.voice_inbox`, writes a
    frontmatter-stamped copy to `raw/voice/`, then archives the source
    under `<voice_inbox>/.processed/`. No state file — the archive move
    is the dedup mechanism.
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
        archive = inbox / ARCHIVE_SUBDIR
        archive.mkdir(exist_ok=True)

        written: list[Path] = []
        errors: list[str] = []
        for src in sources:
            try:
                content = src.read_text(encoding="utf-8").strip()
            except (UnicodeDecodeError, OSError) as exc:
                errors.append(f"{src.name}: read failed ({exc})")
                continue
            if not content:
                errors.append(f"{src.name}: empty file, archived without ingest")
                shutil.move(str(src), str(archive / src.name))
                continue

            captured_at = datetime.fromtimestamp(src.stat().st_mtime, tz=tz)
            out_name = _build_filename(captured_at, content)
            out_path = OUTPUT_DIR / out_name
            # Same-minute slug collision: append seconds.
            if out_path.exists():
                out_path = OUTPUT_DIR / out_name.replace(
                    ".md", f"-{captured_at.strftime('%S')}.md"
                )

            out_path.write_text(
                _build_frontmatter(captured_at, src) + content + "\n",
                encoding="utf-8",
            )
            written.append(out_path)

            try:
                # If archive already has a same-name file (re-run after manual
                # restore), suffix the archive copy with mtime to avoid clobber.
                dest = archive / src.name
                if dest.exists():
                    dest = archive / f"{src.stem}-{int(src.stat().st_mtime)}{src.suffix}"
                shutil.move(str(src), str(dest))
            except OSError as exc:
                errors.append(f"{src.name}: archive failed ({exc})")

        return RunResult(
            files_written=tuple(written),
            files_skipped=len(sources) - len(written),
            message=f"{len(written)} voice note(s) ingested from {inbox}",
            errors=tuple(errors),
        )
