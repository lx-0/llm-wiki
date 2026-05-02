"""Stage/commit/archive transport for session-flush files.

One source of truth for the staged-file lifecycle the LLM Wiki depends on
(.ytstack/KNOWLEDGE.md: "no gap in the chain between capture and persist").

State machine:

    Capture (hooks) ──stage──► SESSIONS_DIR/{prefix}-<sid>-<ts>.md
                                  │
                                  ├── extract OK ─► append_to_daily(...)
                                  │                 mark_complete(staged)
                                  │
                                  └── extract FAIL ─► archive_failure(staged)
                                                      (moved to FAILED_DIR)

    Retry (piggyback) ──pending()──► iterate FAILED_DIR as StagedFlush
                                     same two outcomes as above.

The two hooks (session-end, pre-compact) differ only in:
  - filename prefix (`kind` here)
  - MIN_TURNS_TO_FLUSH threshold (lives in the hooks themselves)

Filename pattern, archive location, and daily-log header format used to be
duplicated across hooks/session-end.py, hooks/pre-compact.py, scripts/flush.py
and scripts/retry-failed-flushes.py — they live here now.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from config import DAILY_DIR, SESSIONS_DIR, TIMEZONE


FAILED_DIR = SESSIONS_DIR / "failed-flushes"

# kind -> filename prefix. Adding a new hook = add an entry here.
KIND_PREFIXES: dict[str, str] = {
    "session-end": "session-flush",
    "pre-compact": "flush-context",
}
_PREFIX_TO_KIND: dict[str, str] = {v: k for k, v in KIND_PREFIXES.items()}

_STAGED_NAME_RE = re.compile(
    r"^(?P<prefix>session-flush|flush-context)-"
    r"(?P<sid>[0-9a-f-]+)-(?P<ts>\d+)\.md$"
)


@dataclass
class StagedFlush:
    """A flush context file staged on disk, awaiting extraction or retry."""
    path: Path
    session_id: str
    kind: str        # "session-end" | "pre-compact"
    created: int     # unix timestamp parsed from filename


def parse_name(path: Path) -> StagedFlush | None:
    """Recognize a staged-flush filename. Returns None if the name doesn't match."""
    m = _STAGED_NAME_RE.match(path.name)
    if not m:
        return None
    kind = _PREFIX_TO_KIND.get(m.group("prefix"))
    if kind is None:
        return None
    return StagedFlush(
        path=path,
        session_id=m.group("sid"),
        kind=kind,
        created=int(m.group("ts")),
    )


def stage(kind: str, session_id: str, content: str) -> StagedFlush:
    """Write a staged-flush file. Returns the StagedFlush handle.

    Used by the two hooks. Caller is responsible for invoking flush.py
    (or whatever consumer) on the returned path.
    """
    if kind not in KIND_PREFIXES:
        raise ValueError(f"unknown flush kind: {kind!r}")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    prefix = KIND_PREFIXES[kind]
    path = SESSIONS_DIR / f"{prefix}-{session_id}-{ts}.md"
    path.write_text(content, encoding="utf-8")
    return StagedFlush(path=path, session_id=session_id, kind=kind, created=ts)


_DAILY_BUTTON_BLOCK = """\
<!-- summarize-button:begin -->
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
<!-- summarize-button:end -->
"""


def append_to_daily(content: str, session_id: str) -> Path:
    """Append extracted content to today's daily log file. Returns the file path.

    On first creation of a daily file, also writes the per-day Summarize
    button block right after the H1 — clicking it from inside that file
    fires `agent-summarize-day-here`, which runs `wiki agent summarize-day
    --var date={{file_basename}}` so the summary targets THAT day, not today.
    """
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(ZoneInfo(TIMEZONE))
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    daily_file = DAILY_DIR / f"{date_str}.md"

    header = f"\n\n---\n\n### Session `{session_id}` — {time_str}\n\n"
    is_new = not daily_file.exists()
    with open(daily_file, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# Daily Log — {date_str}\n\n")
            f.write(_DAILY_BUTTON_BLOCK)
        f.write(header)
        f.write(content)
        f.write("\n")
    return daily_file


def mark_complete(staged: StagedFlush) -> None:
    """Remove the staged file after successful commit to daily/."""
    staged.path.unlink(missing_ok=True)


def archive_failure(staged: StagedFlush) -> Path:
    """Move the staged file to FAILED_DIR for later retry. Returns the new path."""
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = FAILED_DIR / staged.path.name
    staged.path.rename(archive_path)
    staged.path = archive_path
    return archive_path


def pending(limit: int | None = None) -> Iterable[StagedFlush]:
    """Iterate archived flushes that need a retry. Sorted oldest-first."""
    if not FAILED_DIR.exists():
        return []
    out: list[StagedFlush] = []
    for path in sorted(FAILED_DIR.iterdir()):
        if not path.is_file():
            continue
        staged = parse_name(path)
        if staged is None:
            continue
        out.append(staged)
        if limit is not None and len(out) >= limit:
            break
    return out
