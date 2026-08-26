"""`flush_pipeline.pending()` must not silently drop archive files.

Live find 2026-08-26: `sessions/failed-flushes/flush-context.md` (a real,
hand-PII-cleaned context) sat in the retry archive since 2026-07-25. Its name
lacks the `-<sid>-<ts>` suffix, so `parse_name()` returned None and `pending()`
skipped it on every drain — never retried, never reported, invisible. The
archive's whole purpose is "these still need a retry", so an unparseable name
must still be handed to the drain, not dropped.
"""

from __future__ import annotations

import time
from pathlib import Path

import core.flush_pipeline as fp


def _archive(tmp_path: Path, monkeypatch, *names: str) -> Path:
    failed = tmp_path / "failed-flushes"
    failed.mkdir(parents=True)
    for n in names:
        (failed / n).write_text(f"# {n}\n\nbody\n", encoding="utf-8")
    monkeypatch.setattr(fp, "FAILED_DIR", failed)
    return failed


def test_pending_rescues_unparseable_names(tmp_path, monkeypatch):
    _archive(tmp_path, monkeypatch,
             "session-flush-abc-1780000000.md", "flush-context.md")
    got = {s.path.name for s in fp.pending()}
    assert got == {"session-flush-abc-1780000000.md", "flush-context.md"}


def test_rescued_entry_has_a_stable_session_id(tmp_path, monkeypatch):
    """The id wraps the daily-log sentinel block, so a re-run must reuse it
    rather than appending a second block."""
    _archive(tmp_path, monkeypatch, "flush-context.md")
    first = list(fp.pending())[0]
    second = list(fp.pending())[0]
    assert first.session_id == second.session_id
    assert first.session_id


def test_rescued_entry_infers_kind_from_prefix(tmp_path, monkeypatch):
    _archive(tmp_path, monkeypatch, "flush-context.md", "mystery.md")
    by_name = {s.path.name: s for s in fp.pending()}
    assert by_name["flush-context.md"].kind == "pre-compact"
    # Unknown prefix still gets drained; kind falls back to the session shape.
    assert by_name["mystery.md"].kind == "session-end"


def test_rescued_entry_created_from_mtime(tmp_path, monkeypatch):
    failed = _archive(tmp_path, monkeypatch, "flush-context.md")
    stamp = int(time.time()) - 86_400
    import os
    os.utime(failed / "flush-context.md", (stamp, stamp))
    assert list(fp.pending())[0].created == stamp


def test_pending_still_sorts_oldest_first(tmp_path, monkeypatch):
    failed = _archive(tmp_path, monkeypatch,
                      "session-flush-a-1780000000.md",
                      "session-flush-b-1770000000.md",
                      "stray.md")
    now = int(time.time())
    import os
    os.utime(failed / "stray.md", (now, now))
    order = [s.created for s in fp.pending()]
    assert order == sorted(order)


def test_limit_still_honoured(tmp_path, monkeypatch):
    _archive(tmp_path, monkeypatch, "stray-1.md", "stray-2.md", "stray-3.md")
    assert len(list(fp.pending(limit=2))) == 2


def test_directories_are_ignored(tmp_path, monkeypatch):
    failed = _archive(tmp_path, monkeypatch, "flush-context.md")
    (failed / "subdir").mkdir()
    assert [s.path.name for s in fp.pending()] == ["flush-context.md"]
