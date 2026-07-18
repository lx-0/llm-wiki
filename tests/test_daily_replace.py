"""Multi-fire coalescing in flush_pipeline.append_to_daily.

Codex has no SessionEnd event — its `Stop` hook fires per turn, so the same
session flushes many times over its life. append_to_daily must therefore
REPLACE a session's block in today's file (keyed by session_id) instead of
appending a new one each time, or a single Codex session spams N duplicate
blocks. Benign for Claude (one flush per session). See
backlog/codex-session-capture.md.
"""

from __future__ import annotations

from core import daily_capture, flush_pipeline


def test_same_session_replaces_not_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_capture, "DAILY_DIR", tmp_path)
    sid = "019f5ac6-643a-7371-bbe8-54114c79c0fd"

    flush_pipeline.append_to_daily("first capture", sid)
    daily = flush_pipeline.append_to_daily("second capture, grown", sid)

    text = daily.read_text(encoding="utf-8")
    assert text.count(f"<!-- wiki:session {sid} begin -->") == 1, (
        "same session must occupy exactly one block"
    )
    assert "second capture, grown" in text
    assert "first capture" not in text, "stale earlier capture must be replaced"


def test_distinct_sessions_each_get_a_block(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_capture, "DAILY_DIR", tmp_path)
    a = "019f5ac6-643a-7371-bbe8-54114c79c0fd"
    b = "3eb6d245-c729-4fa8-bfce-8b7bd9bc6bfd"  # a Claude UUIDv4

    flush_pipeline.append_to_daily("codex content", a)
    daily = flush_pipeline.append_to_daily("claude content", b)

    text = daily.read_text(encoding="utf-8")
    assert "codex content" in text
    assert "claude content" in text
    assert a in text and b in text


def test_replace_preserves_other_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_capture, "DAILY_DIR", tmp_path)
    a = "019f5ac6-643a-7371-bbe8-54114c79c0fd"
    b = "3eb6d245-c729-4fa8-bfce-8b7bd9bc6bfd"

    flush_pipeline.append_to_daily("codex v1", a)
    flush_pipeline.append_to_daily("claude content", b)
    daily = flush_pipeline.append_to_daily("codex v2", a)  # re-fire of session a

    text = daily.read_text(encoding="utf-8")
    assert "codex v2" in text
    assert "codex v1" not in text
    assert "claude content" in text, "replacing session a must not disturb session b"
    assert text.count(f"<!-- wiki:session {a} begin -->") == 1
