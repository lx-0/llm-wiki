"""Tests for `collectors/scan_calendar.py:CalendarCollector` — Protocol + SQLite scan."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def _seed_calendar_db(db_path: Path, events: list[tuple[str, datetime]]) -> None:
    """Write a minimal Thunderbird-shaped calendar SQLite at db_path.

    cal_events: title, event_start (microseconds since epoch), event_end.
    cal_attendees: icalString.
    """
    db = sqlite3.connect(str(db_path))
    cur = db.cursor()
    cur.execute("CREATE TABLE cal_events (title TEXT, event_start INTEGER, event_end INTEGER)")
    cur.execute("CREATE TABLE cal_attendees (icalString TEXT)")
    for title, dt in events:
        micros = int(dt.timestamp() * 1_000_000)
        cur.execute("INSERT INTO cal_events VALUES (?, ?, ?)", (title, micros, micros))
    cur.execute(
        "INSERT INTO cal_attendees VALUES (?)",
        ("ATTENDEE;CN=Alice Example;mailto:alice@example.com",),
    )
    db.commit()
    db.close()


def test_calendar_collector_registered():
    from collectors import get_collector

    c = get_collector("calendar")
    assert c is not None
    assert c.SPEC.name == "calendar"
    assert c.SPEC.output_subfolder == "raw/notes/calendar"
    assert c.SPEC.piggyback_default is False
    assert c.SPEC.supports_incremental is False


def test_calendar_is_configured_false_when_no_profile(monkeypatch):
    from collectors import scan_calendar

    monkeypatch.setattr(scan_calendar, "_TB_PROFILE_RAW", "")
    monkeypatch.setattr(scan_calendar, "CALENDAR_DB", Path("/nonexistent/cache.sqlite"))

    assert scan_calendar.CalendarCollector().is_configured() is False


def test_calendar_run_skips_when_not_configured(monkeypatch):
    from collectors import scan_calendar

    monkeypatch.setattr(scan_calendar, "_TB_PROFILE_RAW", "")
    monkeypatch.setattr(scan_calendar, "CALENDAR_DB", Path("/nonexistent/cache.sqlite"))

    result = scan_calendar.CalendarCollector().run()
    assert result.files_written == ()
    assert "not configured" in result.message


def test_calendar_run_dry_run_does_not_write(monkeypatch, tmp_path):
    from collectors import scan_calendar

    db_path = tmp_path / "cache.sqlite"
    _seed_calendar_db(db_path, [
        ("Team standup", datetime(2025, 3, 1, 9, 0)),
        ("Customer workshop", datetime(2025, 6, 15, 14, 0)),
    ])

    monkeypatch.setattr(scan_calendar, "_TB_PROFILE_RAW", str(tmp_path))
    monkeypatch.setattr(scan_calendar, "CALENDAR_DB", db_path)
    monkeypatch.setattr(scan_calendar, "REPORT_DIR", tmp_path / "reports")

    result = scan_calendar.CalendarCollector().run(dry_run=True)
    assert result.files_written == ()
    assert result.files_skipped == 1
    assert "[dry-run]" in result.message
    assert "2 events" in result.message
    assert not (tmp_path / "reports").exists()


def test_calendar_run_writes_report(monkeypatch, tmp_path):
    from collectors import scan_calendar

    db_path = tmp_path / "cache.sqlite"
    _seed_calendar_db(db_path, [
        ("Team standup", datetime(2025, 3, 1, 9, 0)),
        ("Another standup", datetime(2026, 1, 10, 9, 0)),
    ])

    monkeypatch.setattr(scan_calendar, "_TB_PROFILE_RAW", str(tmp_path))
    monkeypatch.setattr(scan_calendar, "CALENDAR_DB", db_path)
    monkeypatch.setattr(scan_calendar, "REPORT_DIR", tmp_path / "reports")

    result = scan_calendar.CalendarCollector().run()
    assert len(result.files_written) == 1
    out = result.files_written[0]
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "type: calendar-scan" in content
    assert "Calendar Overview" in content
    # both years present
    assert "2025" in content and "2026" in content


def test_calendar_run_filters_holidays(monkeypatch, tmp_path):
    """Events matching CONFIG.personal.calendar_skip_keywords are dropped."""
    from collectors import scan_calendar

    db_path = tmp_path / "cache.sqlite"
    _seed_calendar_db(db_path, [
        ("Real meeting", datetime(2025, 3, 1, 9, 0)),
        ("Christmas Day", datetime(2025, 12, 25, 0, 0)),
    ])

    monkeypatch.setattr(scan_calendar, "_TB_PROFILE_RAW", str(tmp_path))
    monkeypatch.setattr(scan_calendar, "CALENDAR_DB", db_path)
    monkeypatch.setattr(scan_calendar, "REPORT_DIR", tmp_path / "reports")

    # Patch CONFIG to skip "Christmas"
    class _CONFIG:
        class personal:
            calendar_skip_keywords = ["Christmas"]
            calendar_categories = {}
            calendar_work_keywords = []
            calendar_report_language = "en"
    monkeypatch.setattr(scan_calendar, "CONFIG", _CONFIG)

    data = scan_calendar.scan_calendar(db_path)
    assert data["total_events"] == 1  # Christmas filtered out


def test_calendar_categorize_event(monkeypatch):
    from collectors import scan_calendar

    class _CONFIG:
        class personal:
            calendar_categories = {"Health": ["doctor", "dentist"]}
            calendar_work_keywords = ["acme"]
            calendar_skip_keywords = []
            calendar_report_language = "en"
    monkeypatch.setattr(scan_calendar, "CONFIG", _CONFIG)

    assert scan_calendar.categorize_event("Dentist appointment") == "Health"
    assert scan_calendar.categorize_event("ACME sync") == "Work / Workshops"
    assert scan_calendar.categorize_event("Random thing") == "Other"


def test_calendar_parse_attendee_ical():
    from collectors import scan_calendar

    assert scan_calendar.parse_attendee_ical("ATTENDEE;CN=Bob:mailto:bob@x.com") == "Bob"
    assert scan_calendar.parse_attendee_ical("ATTENDEE:mailto:carol@x.com") == "carol@x.com"
    # google-calendar synthetic addresses are filtered
    assert scan_calendar.parse_attendee_ical("ATTENDEE:mailto:abc@calendar.google.com") is None
