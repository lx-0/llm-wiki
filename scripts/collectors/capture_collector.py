"""Capture intake — folder-watching collector for quick-capture notes (M025).

The spine of the quick-capture-correction loop. The operator one-taps cryptic
notes / article snippets into the configured `personal.capture_inbox` directory
(any tool that writes `.txt` / `.md` / `.html` works — a WhatsApp-self-group
export, a Notion quick-note sync, a shortcut that drops a file). This collector
picks them up, assigns a *deterministic, content-derived capture-ID*, writes a
frontmatter-stamped note into `raw/captures/`, and archives the source under
`raw/inbox-mobile/captures/` (vault-internal audit zone, M022 two-zone intake).

Structurally a sibling of `collectors/voice.py`, with two deliberate
divergences:

- **Stable capture-ID** = first 12 hex of `sha256(content.strip())`. Same
  content → same ID; edited content → a new ID (correctly a new capture).
  This ID is the join-key the correction loop uses: the digest surfaces a
  capture by ID, and the operator overturns a wrong reading by quoting it.
  Collision across two genuinely-distinct captures with byte-identical text
  is accepted for v1 (re-drops are the common case; true collisions are not).
- **ID-derived filename** `capture-<id12>.md`, so a re-drop of identical
  content OVERWRITES the same article rather than spawning a duplicate
  (voice keys on timestamp+slug and lets identical notes coexist). No
  punctuation pass — captures may be article snippets; the body stays raw.

`state/capture_index.json` (the ID→source/article map) is written here at
ingest via `core.capture_index.record()` (T03) — the bridge the correction
loop consumes (S02 forward-link, S03 supersede). The piggyback override knob,
`config.example.yaml` docs and `templates/` sync shipped in T02.
See `.ytstack/M025-S01-PLAN.md`.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import CollectorSpec, RunResult, register
from core import capture_index, daily_capture
from core.config import CONFIG, TIMEZONE
from core.paths import RAW_DIR

log = logging.getLogger(__name__)

OUTPUT_DIR = RAW_DIR / "captures"
MOBILE_ARCHIVE_DIR = RAW_DIR / "inbox-mobile" / "captures"
ACCEPTED_SUFFIXES = (".txt", ".md", ".html")
CAPTURE_ID_LEN = 12


def _capture_id(content: str) -> str:
    """Deterministic capture-ID = first 12 hex of sha256(content.strip()).

    Whitespace-insensitive at the edges so a trailing newline doesn't fork
    the ID. Same content → same ID (idempotent re-drop); edited content →
    new ID (a genuinely new capture).
    """
    digest = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
    return digest[:CAPTURE_ID_LEN]


def _inbox_path() -> Path | None:
    raw = (CONFIG.personal.capture_inbox or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _build_frontmatter(
    capture_id: str, captured_at: datetime, source: Path, *, corrects: str | None = None
) -> str:
    lines = [
        "---",
        "type: capture",
        "origin: capture-intake",
        f"capture_id: {capture_id}",
        f"captured_at: {captured_at.isoformat()}",
        f"source: {source.name}",
    ]
    if corrects:
        # This capture opened with a `re:/corrects:<id>` reference to a known capture —
        # mark it a correction targeting that interpretation (the supersede write-back
        # is S03; here we only recognise + tag).
        lines.append("kind: correction")
        lines.append(f"corrects: {corrects}")
    lines += [
        "tags: [capture]",
        "---",
        "",
    ]
    return "\n".join(lines) + "\n"


def _scan_inbox(inbox: Path) -> list[Path]:
    """List inbox files eligible for ingest. Skips dot-files, sub-dirs, and
    anything whose suffix isn't .txt / .md / .html."""
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


def _append_daily_rollup(
    capture_id: str, captured_at: datetime, content: str, out_path: Path
) -> None:
    """Append a capture-intake one-liner to daily/<date>/captures.md.

    Surfaces one line per capture: time, ID, first few words, link back to
    the canonical raw/captures/ file. Failures are swallowed — the rollup is
    a side-effect, never break the primary write.
    """
    date_iso = captured_at.strftime("%Y-%m-%d")
    time_label = captured_at.strftime("%H:%M")
    first_line = content.splitlines()[0].strip() if content else "(empty)"
    if len(first_line) > 80:
        first_line = first_line[:77].rstrip() + "…"
    line = f"- **{time_label}** · `{capture_id}` · {first_line} → [[{out_path.stem}]]"
    try:
        daily_capture.append(date_iso, "captures", line)
    except Exception:  # noqa: BLE001
        log.exception("daily-rollup append failed for capture %s", out_path.name)


@register
class CaptureCollector:
    """Quick-capture intake — inbox-watching, content-ID'd note ingester.

    Reads any `*.txt` / `*.md` / `*.html` from `personal.capture_inbox`,
    writes a frontmatter-stamped note to `raw/captures/capture-<id>.md`
    (filename derived from a content hash so re-drops are idempotent), then
    archives the source under `raw/inbox-mobile/captures/` (vault-internal).
    The archive move is the per-source dedup mechanism; the content-hash
    filename is the per-content dedup mechanism.
    """

    SPEC = CollectorSpec(
        name="capture",
        output_subfolder="raw/captures",
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
            return RunResult(
                message="capture_inbox not configured (personal.capture_inbox is empty)"
            )
        if not inbox.exists():
            return RunResult(message=f"capture_inbox not found: {inbox}")

        tz = ZoneInfo(TIMEZONE)
        sources = _scan_inbox(inbox)
        if not sources:
            return RunResult(message=f"no new captures in {inbox}")

        if dry_run:
            return RunResult(
                files_skipped=len(sources),
                message=f"[dry-run] would ingest {len(sources)} capture(s) from {inbox}",
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        MOBILE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        errors: list[str] = []
        # Snapshot known capture ids once — a correction references a PRIOR capture,
        # already indexed before this run (corrections are async by design).
        known_ids = set(capture_index.load().keys())
        for src in sources:
            try:
                raw = src.read_text(encoding="utf-8").strip()
            except (UnicodeDecodeError, OSError) as exc:
                errors.append(f"{src.name}: read failed ({exc})")
                continue
            if not raw:
                errors.append(f"{src.name}: empty file, archived without ingest")
                self._archive(src, errors)
                continue

            capture_id = _capture_id(raw)
            corrects = capture_index.detect_correction(raw, known_ids=known_ids)
            captured_at = datetime.fromtimestamp(src.stat().st_mtime, tz=tz)
            # Filename is ID-derived: a re-drop of identical content lands on
            # the same path and overwrites, rather than spawning a duplicate.
            out_path = OUTPUT_DIR / f"capture-{capture_id}.md"
            out_path.write_text(
                _build_frontmatter(capture_id, captured_at, src, corrects=corrects) + raw + "\n",
                encoding="utf-8",
            )
            written.append(out_path)

            # Register in the capture index (the correction-loop bridge). The
            # article is already on disk — an index miss is degraded, not fatal,
            # so surface it via errors and keep the batch alive.
            try:
                capture_index.record(
                    capture_id,
                    source_path=str(out_path.relative_to(RAW_DIR.parent)),
                    created=captured_at.isoformat(),
                )
            except Exception:  # noqa: BLE001
                errors.append(f"{src.name}: capture-index write failed")
                log.exception("capture-index record failed for %s", out_path.name)

            _append_daily_rollup(capture_id, captured_at, raw, out_path)
            self._archive(src, errors)

        return RunResult(
            files_written=tuple(written),
            files_skipped=len(sources) - len(written),
            message=f"{len(written)} capture(s) ingested from {inbox}",
            errors=tuple(errors),
        )

    @staticmethod
    def _archive(src: Path, errors: list[str]) -> None:
        """Move a processed source into the vault audit zone. On same-name
        collision (re-run after manual restore), suffix with mtime."""
        try:
            dest = MOBILE_ARCHIVE_DIR / src.name
            if dest.exists():
                dest = MOBILE_ARCHIVE_DIR / f"{src.stem}-{int(src.stat().st_mtime)}{src.suffix}"
            shutil.move(str(src), str(dest))
        except OSError as exc:
            errors.append(f"{src.name}: archive failed ({exc})")
