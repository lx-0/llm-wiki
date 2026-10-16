"""A retried flush lands under the day its context was staged, not the day of the retry.

Live find (M034-S06-T07): `append_to_daily` dated every block `datetime.now()`, so the
retry piggyback filed weeks-old contexts into the retry day's `daily/<today>/sessions.md`
— session 5702d317, staged 2026-09-12, was retried into daily/2026-10-15. A session already
captured on its own day was written a second time, under the wrong date.

On its own day a retry meets the session's block if one exists (Codex flushes on every
turn; Claude flushes before a compaction and at the end). The newer content wins: the retry
replaces an older block and leaves a newer one alone.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import core.daily_capture as daily_capture
import core.flush_pipeline as fp
import retry_failed_flushes as retry
from core.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


@pytest.fixture
def vault(tmp_path, monkeypatch):
    daily = tmp_path / "daily"
    failed = tmp_path / "failed-flushes"
    daily.mkdir()
    failed.mkdir()
    monkeypatch.setattr(daily_capture, "DAILY_DIR", daily)
    monkeypatch.setattr(fp, "FAILED_DIR", failed)
    seen: list[str] = []

    async def fake_extract(context: str) -> str:
        seen.append(context)
        return f"## Summary\n\nDistilled from: {context.strip()}"

    monkeypatch.setattr(retry, "extract_from_context", fake_extract)
    return daily, failed, seen


def _archived(failed: Path, sid: str, when: datetime, body: str = "the context") -> fp.StagedFlush:
    path = failed / f"session-flush-{sid}-{int(when.timestamp())}.md"
    path.write_text(body + "\n", encoding="utf-8")
    staged = fp.parse_name(path)
    assert staged is not None
    return staged


def _sessions(daily: Path, date: str) -> str:
    return (daily / date / "sessions.md").read_text(encoding="utf-8")


def test_a_retry_files_the_session_under_its_staged_day(vault):
    daily, failed, _seen = vault
    staged = _archived(failed, "5702d317", datetime(2026, 9, 12, 0, 10, tzinfo=TZ))

    assert asyncio.run(retry.retry_one(staged, dry_run=False)) is True

    text = _sessions(daily, "2026-09-12")
    assert "<!-- wiki:session 5702d317 begin -->" in text
    assert "### Session `5702d317` — 00:10:00" in text
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    assert not (daily / today / "sessions.md").exists()
    assert not staged.path.exists()


def test_a_retry_leaves_a_newer_block_of_the_session_alone(vault):
    daily, failed, seen = vault
    day = datetime(2026, 9, 12, 9, 0, tzinfo=TZ)
    fp.append_to_daily("the later turn's distill", "abc", when=day.replace(hour=18))
    staged = _archived(failed, "abc", day, body="an earlier turn")

    assert asyncio.run(retry.retry_one(staged, dry_run=False)) is True

    text = _sessions(daily, "2026-09-12")
    assert "the later turn's distill" in text
    assert "an earlier turn" not in text
    assert seen == [], "no extraction is spent on a context the day already holds newer"
    assert not staged.path.exists()


def test_a_retry_replaces_an_older_block_of_the_session(vault):
    daily, failed, _seen = vault
    day = datetime(2026, 9, 12, 9, 0, tzinfo=TZ)
    fp.append_to_daily("the pre-compact distill", "abc", when=day)
    staged = _archived(failed, "abc", day.replace(hour=17), body="the whole session")

    assert asyncio.run(retry.retry_one(staged, dry_run=False)) is True

    text = _sessions(daily, "2026-09-12")
    assert "the whole session" in text
    assert "the pre-compact distill" not in text
    assert text.count("<!-- wiki:session abc begin -->") == 1


def test_an_archive_without_a_usable_time_goes_to_today(vault):
    daily, failed, _seen = vault
    path = failed / "flush-context.md"
    path.write_text("a rescued context\n", encoding="utf-8")
    staged = fp.StagedFlush(path=path, session_id="rescued-x", kind="pre-compact", created=0)

    assert asyncio.run(retry.retry_one(staged, dry_run=False)) is True

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    assert "a rescued context" in _sessions(daily, today)
