"""The session-start hook injects the operator's recent activity: the day's session log.

Since the 2026-05-15 rollup the session log is `daily/<date>/sessions.md`, and
`daily/<date>.md` is the digest the daily-digest agent writes the day AFTER. The hook still
read `daily/<date>.md`, so today's sessions never reached a new agent session, and the tail
stayed empty until yesterday's digest existed (M034-S06-T07; the same class as the home
screen's pre-rollup probe, c5f597c).
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "session-start.py"


@pytest.fixture
def hook(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("session_start_hook", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DAILY_DIR", tmp_path / "daily")
    return module


def _day(delta: int = 0) -> str:
    return (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_today_session_log_reaches_the_session(hook):
    _write(
        hook.DAILY_DIR / _day() / "sessions.md", "# Daily Sessions\n\nworked on the dispatcher\n"
    )

    out = hook.read_recent_daily()

    assert f"# Recent Daily Log ({_day()})" in out
    assert "worked on the dispatcher" in out


def test_without_a_session_today_yesterday_is_used(hook):
    _write(hook.DAILY_DIR / _day(1) / "sessions.md", "yesterday's sessions\n")

    assert "yesterday's sessions" in hook.read_recent_daily()


def test_the_digest_is_the_fallback_for_a_day_without_a_session_log(hook):
    _write(hook.DAILY_DIR / f"{_day(1)}.md", "yesterday's digest\n")

    assert "yesterday's digest" in hook.read_recent_daily()


def test_nothing_recent_injects_nothing(hook):
    assert hook.read_recent_daily() == ""
