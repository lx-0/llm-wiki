"""What a flush does with each extraction outcome (M034-S06-T07).

A distill becomes the session's daily block; `NOTHING_TO_SAVE` consumes the context and
writes nothing; a failure archives the context for the retry drain. The drain mirrors that
and says how deep its queue is: it takes five per run, and with 353 contexts waiting in the
live archive (2026-10-16) it logged "Found 5 archived flush(es)".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import pytest

import core.flush_pipeline as fp
import flush
import retry_failed_flushes as retry
from core import daily_capture


@pytest.fixture
def vault(tmp_path, monkeypatch):
    daily = tmp_path / "daily"
    failed = tmp_path / "failed-flushes"
    daily.mkdir()
    failed.mkdir()
    monkeypatch.setattr(daily_capture, "DAILY_DIR", daily)
    monkeypatch.setattr(fp, "FAILED_DIR", failed)
    monkeypatch.setattr(flush, "setup_console_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(flush, "_is_duplicate", lambda _sid: False)
    monkeypatch.setattr(flush, "_record_flush", lambda _sid: None)
    # A written block goes on to history, compile, dashboards and piggybacks — never here.
    for name in (
        "maybe_trigger_compile",
        "refresh_dashboard_stats",
        "refresh_dashboard_lint",
        "maybe_run_piggyback_tasks",
    ):
        monkeypatch.setattr(flush, name, lambda *_a, _n=name: pytest.fail(f"{_n} ran"))
    monkeypatch.setattr("core.utils.append_history", lambda *_a, **_k: pytest.fail("history"))
    return daily, failed


def _flush(monkeypatch, context: Path, reply: str | None) -> None:
    async def fake_extract(_context: str) -> str | None:
        return reply

    monkeypatch.setattr(flush, "extract_from_context", fake_extract)
    monkeypatch.setattr(flush.sys, "argv", ["flush.py", str(context), "abc1"])
    asyncio.run(flush.main())


def _staged(root: Path) -> Path:
    path = root / f"session-flush-abc1-{int(datetime.now().timestamp())}.md"
    path.write_text("a conversation\n", encoding="utf-8")
    return path


def test_nothing_to_save_consumes_the_context_and_writes_no_block(vault, tmp_path, monkeypatch):
    daily, failed = vault
    context = _staged(tmp_path)
    _flush(monkeypatch, context, flush.NOTHING_TO_SAVE)
    assert not context.exists()
    assert list(failed.iterdir()) == [], "nothing to save is no failure to retry"
    assert list(daily.rglob("*.md")) == []


def test_a_failed_extraction_archives_the_context(vault, tmp_path, monkeypatch):
    daily, failed = vault
    context = _staged(tmp_path)
    _flush(monkeypatch, context, None)
    assert [p.name for p in failed.iterdir()] == [context.name]
    assert list(daily.rglob("*.md")) == []


def _archived(failed: Path, sid: str, stamp: int) -> fp.StagedFlush:
    path = failed / f"session-flush-{sid}-{stamp}.md"
    path.write_text("the context\n", encoding="utf-8")
    staged = fp.parse_name(path)
    assert staged is not None
    return staged


def test_the_drain_drops_a_context_with_nothing_to_save(vault, monkeypatch):
    daily, failed = vault

    async def nothing(_context: str) -> str:
        return flush.NOTHING_TO_SAVE

    monkeypatch.setattr(retry, "extract_from_context", nothing)
    staged = _archived(failed, "abc", 1789229524)
    assert asyncio.run(retry.retry_one(staged, dry_run=False)) is True
    assert not staged.path.exists()
    assert list(daily.rglob("*.md")) == []


def test_the_drain_reports_the_queue_depth(vault, monkeypatch, caplog):
    _daily, failed = vault
    for n in range(7):
        _archived(failed, f"a{n}", 1789229524 + n)
    tried: list[str] = []

    async def fake_retry(staged: fp.StagedFlush, dry_run: bool) -> bool:
        tried.append(staged.session_id)
        return False

    monkeypatch.setattr(retry, "retry_one", fake_retry)
    with caplog.at_level(logging.INFO, logger="retry-failed-flushes"):
        asyncio.run(retry.main_async(dry_run=False, limit=5))
    assert tried == ["a0", "a1", "a2", "a3", "a4"], "oldest first, five per run"
    assert "Found 7 archived flush(es) — retrying 5 this run" in caplog.text
