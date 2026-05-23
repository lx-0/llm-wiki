"""Capture index — the `capture_id → {source_path, created, status}` map (M025).

The bridge the quick-capture-correction loop is built on. The capture collector
calls `record()` at ingest to register each new capture; downstream consumers
read the map via `load()`:

  - S02 (forward link): the daily-digest resolves a capture-ID to its raw
    article (and, later, the compiled interpretation).
  - S03 (supersede): an operator correction quoting a capture-ID flips that
    entry's `status` to "superseded", which the next compile cycle honours.

Idempotent on re-ingest: a re-drop of identical content yields the same
capture-ID, and `record()` leaves any existing entry untouched — so a
"superseded" status set by S03 is NOT reset to "open" by a re-ingest.

Concurrency: the read-modify-write runs under an fcntl flock (same pattern as
`core.usage` / `core.daily_capture`), so parallel collector runs / SessionEnd
flushes can't corrupt the file.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager

from .paths import STATE_DIR
from .utils import load_json_state, save_json_state

CAPTURE_INDEX_FILE = STATE_DIR / "capture_index.json"
_LOCK_FILE = STATE_DIR / "capture_index.lock"

STATUS_OPEN = "open"
STATUS_SUPERSEDED = "superseded"


@contextmanager
def _locked():
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = open(_LOCK_FILE, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


def load() -> dict[str, dict]:
    """Return the `capture_id → entry` map ({} if absent or unreadable).

    A corrupt / partially-written file is treated as empty rather than crashing
    the ingest path — the next `record()` rewrites it cleanly.
    """
    try:
        return load_json_state(CAPTURE_INDEX_FILE)
    except (ValueError, OSError):
        return {}


def record(capture_id: str, *, source_path: str, created: str) -> bool:
    """Register a capture at ingest. Idempotent: if `capture_id` is already
    present the existing entry (including any S03-set `status`) is preserved and
    this returns False. Returns True when a new entry was added.
    """
    with _locked():
        index = load()
        if capture_id in index:
            return False
        index[capture_id] = {
            "source_path": source_path,
            "created": created,
            "status": STATUS_OPEN,
        }
        save_json_state(CAPTURE_INDEX_FILE, index)
        return True
