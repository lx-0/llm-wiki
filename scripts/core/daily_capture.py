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

Four semantics, all under the same per-(date, source) flock:

- `append(date, source, content)` — for streaming inputs that produce
  multiple entries per day (voice intakes as they land, gmeet/jamie
  meetings arriving one at a time). Each call appends a newline-terminated
  block.
- `append_with_source(date, source, line, source_ref)` — `append` plus a
  frontmatter `sources:` provenance entry.
- `replace_section(date, source, content)` — for one-shot-per-run
  inputs that produce a single coherent block per collector pass
  (health-collector's daily Oura snapshot; email-collector's delta
  summary). Each call atomically replaces the file's content.
- `replace_block(date, source, begin, end, block, ...)` — insert-or-replace
  a single sentinel-bracketed block keyed by its markers, leaving every
  other block in the same file untouched. This is how the sessions hook
  writes `daily/<date>/sessions.md`: each session owns one
  `<!-- wiki:session <id> begin/end -->` region, replaced in place when the
  same session re-flushes (Codex fires a `Stop` hook per turn) instead of
  spamming duplicate blocks. Routing it through this module closes the last
  bypass of the one-writer-per-(date, source) invariant — sessions is the
  highest-concurrency source, and its old unlocked read-splice-write path
  (in flush_pipeline) could silently drop a concurrently-appended block.

The root `daily/<date>.md` digest is **not** written by this module —
that's compile.py's job (Phase 3). This helper only owns the
per-source subfolder.
"""

from __future__ import annotations

import fcntl
import re
from datetime import date as _date
from pathlib import Path

from core import markers
from core.paths import ROOT_DIR

# Configured at import time so tests can monkey-patch.
DAILY_DIR: Path = ROOT_DIR / "daily"

# ── Summarize-this-day button (single source of truth) ────────────────
# The per-day Meta-Bind button that fires the `summarize-day` agent against the
# file it lives in. Written once at the top of `daily/<date>/sessions.md` on
# first creation (via `replace_block` from flush_pipeline) and back-filled into
# legacy `daily/*.md` by `scripts/dashboard/inject_daily_button.py`. Both write
# sites import THIS constant so the block can never drift between them.
SUMMARIZE_BUTTON_BEGIN = "<!-- summarize-button:begin -->"
SUMMARIZE_BUTTON_END = "<!-- summarize-button:end -->"
SUMMARIZE_BUTTON_BLOCK = f"""\
{SUMMARIZE_BUTTON_BEGIN}
```meta-bind-button
label: 📅 Summarize this day
hidden: false
class: ""
tooltip: "Run summarize-day agent against this day's log."
id: btn-summarize-here
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: agent summarize this day"
```
{SUMMARIZE_BUTTON_END}"""

# Allow-list. New collectors that want to write into daily/ MUST extend
# this set explicitly — silent additions are a footgun.
KNOWN_SOURCES: frozenset[str] = frozenset({
    "sessions",  # Claude Code session-end hook (was the old daily/<date>.md content)
    "health",    # collectors/health.py (Oura daily rollup; replace-per-run)
    "meetings",  # collectors/{gmeet,jamie}.py (append per meeting)
    "voice",     # collectors/voice.py (append per intake)
    "email",     # collectors/email_collector.py (replace per delta-run)
    "pictures",  # collectors/pictures.py (append per intake)
    "captures",  # collectors/capture_collector.py (append per intake, M025)
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


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n?(.*)\Z", re.DOTALL)


def _read_sources_and_body(text: str) -> tuple[list[str], str]:
    """Split a daily-source file into (existing `sources:` list, body).

    Only the `sources:` block is understood; any other frontmatter keys are
    preserved verbatim by being re-emitted around the merged list. Files with
    no frontmatter return ([], full-text-as-body).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return [], text
    fm_raw, body = m.group(1), m.group(2)
    sources: list[str] = []
    in_sources = False
    other_lines: list[str] = []
    for line in fm_raw.splitlines():
        if line.strip() == "sources:" or line.rstrip() == "sources:":
            in_sources = True
            continue
        if in_sources and line.lstrip().startswith("- "):
            sources.append(line.lstrip()[2:].strip())
            continue
        in_sources = False
        if line.strip():
            other_lines.append(line)
    # Re-attach non-sources frontmatter to the body so it survives the rewrite.
    if other_lines:
        body = "---\n" + "\n".join(other_lines) + "\n---\n" + body
    return sources, body


def append_with_source(
    date_iso: str, source: str, line: str, source_ref: str
) -> Path:
    """Append a body `line` AND record `source_ref` in the file's frontmatter.

    For substrates that want provenance to the canonical `raw/` file without
    a body wikilink (Obsidian ignores `raw/`, so an in-body `[[…]]` renders
    dead). The reference lives in a frontmatter `sources:` list — not a graph
    edge, no `raw/`-index cost, machine-readable provenance.

    Read-modify-write under the same flock as `append()`: reads the current
    file, merges `source_ref` into the `sources:` list (dedup, append order),
    appends the body line, rewrites the whole file. Per-day volume is small
    (one file per source per day) so the rewrite cost is negligible.
    """
    target = _resolve_path(date_iso, source)
    if not line.endswith("\n"):
        line = line + "\n"

    with open(target, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            current = fh.read()
            sources, body = _read_sources_and_body(current)
            if source_ref not in sources:
                sources.append(source_ref)
            if body and not body.endswith("\n"):
                body += "\n"
            fm = "---\nsources:\n" + "".join(f"  - {s}\n" for s in sources) + "---\n"
            new_text = fm + body + line
            fh.seek(0)
            fh.truncate()
            fh.write(new_text)
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


def replace_block(
    date_iso: str,
    source: str,
    begin: str,
    end: str,
    block: str,
    *,
    create_header: str = "",
) -> Path:
    """Insert-or-replace one sentinel-bracketed `block` in `daily/<date>/<source>.md`.

    `block` must carry the `begin` … `end` markers itself and end with a newline.
    The whole read-modify-write runs under the same flock as `append()`, so two
    concurrent writers of the same (date, source) — the session hook firing on
    close while a Codex `Stop`-hook re-flush lands, or two first-flushes of a new
    day — can never lose each other's block. Semantics:

    - **file empty / new** → write `create_header` + `block`.
    - **block present** → replace the region in place (reversed-marker safe via
      `markers.find_region`; the region's trailing newline is normalized so
      repeated replaces of the same key don't accrete blank lines).
    - **block absent** → append the block after a single blank-line separator.

    `date_iso` is supplied by the caller (not derived from `today_iso()`) so a
    timezone-aware date computed at the write site flows straight through — a
    session that closes just after midnight lands in the correct day file.
    """
    target = _resolve_path(date_iso, source)
    if not block.endswith("\n"):
        block = block + "\n"

    # a+ so the FD is positioned for both read (current content) and the
    # truncating rewrite, all inside one lock hold.
    with open(target, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            current = fh.read()
            if not current:
                new_text = create_header + block
            else:
                region = markers.find_region(current, begin, end)
                if region is not None:
                    new_text = (
                        current[: region.start]
                        + block.rstrip("\n")
                        + current[region.end :]
                    )
                else:
                    sep = "" if current.endswith("\n") else "\n"
                    new_text = current + sep + "\n" + block
            fh.seek(0)
            fh.truncate()
            fh.write(new_text)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return target
