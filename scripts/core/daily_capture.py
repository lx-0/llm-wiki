"""Per-source append-only writer for `daily/<date>/<source>.md` files.

This module is the single chokepoint for **all** writes into the new
per-day subfolder substrate (post-2026-05-15 `daily/`-as-rollup arc —
see `.ytstack/AD-HOC-daily-as-rollup-PLAN.md`). Each substrate-source
(sessions / health / meetings / voice / email) owns ONE file per day
inside `daily/<YYYY-MM-DD>/`; this helper enforces:

- One writer per (date, source) pair via fcntl-flock — no corruption
  if a hook fires while a collector is mid-write.
- Subfolder created lazily on first write.
- Source-name validation against `KNOWN_SOURCES` — typo-protection
  (a stray "voic" instead of "voice" would silently create the wrong
  file otherwise).
- Path-traversal protection: source names are matched against a
  conservative regex so caller-poisoning is impossible.

Two semantics:

- `append(date, source, content)` — for streaming inputs that produce
  multiple entries per day (voice intakes as they land, session-end
  hook firing on each session close, gmeet/jamie meetings arriving
  one at a time). Each call appends a newline-terminated block.
- `replace_section(date, source, content)` — for one-shot-per-run
  inputs that produce a single coherent block per collector pass
  (health-collector's daily Oura snapshot; email-collector's delta
  summary). Each call atomically replaces the file's content.

The root `daily/<date>.md` digest is **not** written by this module —
that's compile.py's job (Phase 3). This helper only owns the
per-source subfolder.
"""

from __future__ import annotations

import fcntl
import re
from datetime import date as _date
from pathlib import Path

from core.paths import ROOT_DIR

# Configured at import time so tests can monkey-patch.
DAILY_DIR: Path = ROOT_DIR / "daily"

# Allow-list. New collectors that want to write into daily/ MUST extend
# this set explicitly — silent additions are a footgun.
KNOWN_SOURCES: frozenset[str] = frozenset({
    "sessions",  # Claude Code session-end hook (was the old daily/<date>.md content)
    "health",    # collectors/health.py (Oura daily rollup; replace-per-run)
    "meetings",  # collectors/{gmeet,jamie}.py (append per meeting)
    "voice",     # collectors/voice.py (append per intake)
    "email",     # collectors/email_collector.py (replace per delta-run)
    "pictures",  # collectors/pictures.py (append per intake)
})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_SOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def today_iso() -> str:
    """ISO 8601 date for 'now', operator's local timezone.

    Mirrors `core.utils.now_iso()[:10]` semantics — kept here as a
    thin wrapper so callers don't import core.utils just for the date.
    """
    return _date.today().isoformat()


def _validate_date(date_iso: str) -> None:
    if not isinstance(date_iso, str) or not _ISO_DATE_RE.match(date_iso):
        raise ValueError(
            f"daily_capture: expected ISO date YYYY-MM-DD, got {date_iso!r}"
        )


def _validate_source(source: str) -> None:
    if not isinstance(source, str) or not _SAFE_SOURCE_RE.match(source):
        raise ValueError(
            f"daily_capture: source {source!r} has unsafe shape; expected "
            "lowercase + digits + underscore/hyphen, starting with a letter."
        )
    if source not in KNOWN_SOURCES:
        raise ValueError(
            f"daily_capture: unknown source {source!r}. Extend KNOWN_SOURCES "
            f"if this is a new substrate. Current: {sorted(KNOWN_SOURCES)}"
        )


def ensure_subfolder(date_iso: str) -> Path:
    """Idempotently mkdir `<DAILY_DIR>/<date>/`. Returns the path."""
    _validate_date(date_iso)
    subfolder = DAILY_DIR / date_iso
    subfolder.mkdir(parents=True, exist_ok=True)
    return subfolder


def _resolve_path(date_iso: str, source: str) -> Path:
    _validate_date(date_iso)
    _validate_source(source)
    subfolder = ensure_subfolder(date_iso)
    return subfolder / f"{source}.md"


def append(date_iso: str, source: str, content: str) -> Path:
    """Append `content` to `daily/<date>/<source>.md`. Lock-protected.

    Adds a trailing newline if the content doesn't already have one,
    so consecutive append-lines stay separated by exactly one newline
    (no double-blank-lines).
    """
    target = _resolve_path(date_iso, source)
    if not content.endswith("\n"):
        content = content + "\n"

    # Open for append; fcntl-lock the FD before writing; release on close.
    with open(target, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(content)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return target


def replace_section(date_iso: str, source: str, content: str) -> Path:
    """Atomically replace `daily/<date>/<source>.md` with `content`.

    For collectors whose pass produces one coherent block (Oura daily
    snapshot, email delta summary). Last-write-wins per (date, source).
    """
    target = _resolve_path(date_iso, source)
    if not content.endswith("\n"):
        content = content + "\n"

    # Open for write (truncates); lock before writing.
    with open(target, "w", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(content)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return target
