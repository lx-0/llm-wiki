"""Tests for the Google Calendar collector (collectors/calendar_collector.py).

Replaces the M005-era Thunderbird-SQLite scan tests. The new collector is
a real substrate (Google Calendar v3 via OAuth); tests wrap it with a
fake HTTP client + an isolated tmp_path vault and exercise the pure
pieces of the pipeline:

- Registry: ``get_collector("calendar")`` resolves to the new
  ``CalendarCollector`` and the legacy ``scan_calendar`` module is gone.
- Account resolution: ``_resolve_calendar_accounts`` discriminates on
  ``kind: google-calendar`` under ``personal.accounts.<id>.calendar``.
- Event filtering: cancelled, declined, holiday-keyword filtering.
- Per-date rollup shape: frontmatter, event blocks, sentinel-delimited
  managed region, operator-prose preservation.
- Recurring-event collapse: ``recurringEventId`` triggers a
  ``knowledge/concepts/<slug>.md`` write and per-date references.
- Transcript cross-link: same-date title-slug overlap attaches a
  ``Transcript:`` line.
- Multi-calendar selection: ``include:`` list, ``selected: true``
  fallback, primary-only fallback.
- Bootstrap delegation: ``calendar-auth`` routes through
  ``google_oauth.bootstrap`` with the calendar.readonly scope.
- Full end-to-end run with a fake client writes per-date markdown and
  persists per-calendar etag state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from collectors import calendar_collector as cal


# ── Registry / Spec ─────────────────────────────────────────────────


def test_calendar_collector_registered():
    from collectors import get_collector

    c = get_collector("calendar")
    assert c is not None
    assert c.SPEC.name == "calendar"
    assert c.SPEC.output_subfolder == "raw/notes/calendar"
    assert c.SPEC.piggyback_default is True
    assert c.SPEC.supports_incremental is True
    assert c.SPEC.supports_account_loop is True


def test_legacy_scan_calendar_module_removed():
    """The Thunderbird-SQLite stub is gone; importing it must fail."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("collectors.scan_calendar")


def test_collector_filename_avoids_stdlib_shadow():
    """`scripts/collectors/calendar.py` would shadow Python's stdlib `calendar`
    via `http.cookiejar`'s `from calendar import timegm` whenever
    `scripts/collectors/` ends up on sys.path (which happens when `cli.py`
    is invoked directly). The filename must carry the `_collector` suffix.
    Same fix pattern as `email_collector.py` (pre-existing)."""
    import collectors

    assert hasattr(collectors, "calendar_collector"), (
        "calendar_collector module missing — was it renamed back to calendar.py? "
        "That shadows stdlib calendar via http.cookiejar."
    )
    # Stdlib `calendar` must still be reachable.
    import calendar as stdlib_calendar
    from calendar import timegm  # noqa: F401 — what http.cookiejar does
    assert callable(stdlib_calendar.timegm)


# ── Time parsing ────────────────────────────────────────────────────


def test_parse_event_time_datetime():
    dt, all_day = cal._parse_event_time({"dateTime": "2026-05-15T09:00:00+02:00"})
    assert dt is not None
    assert dt.hour == 9
    assert all_day is False


def test_parse_event_time_all_day():
    dt, all_day = cal._parse_event_time({"date": "2026-05-15"})
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 15
    assert all_day is True


def test_parse_event_time_malformed_returns_none():
    dt, all_day = cal._parse_event_time({"dateTime": "not-a-date"})
    assert dt is None
    assert all_day is False
    dt2, _ = cal._parse_event_time(None)
    assert dt2 is None


def test_format_event_window_renders_range():
    start = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 15, 9, 30, tzinfo=timezone.utc)
    assert cal._format_event_window(start, end, all_day=False) == "09:00–09:30"


def test_format_event_window_all_day():
    start = datetime(2026, 5, 15, tzinfo=timezone.utc)
    assert cal._format_event_window(start, None, all_day=True) == "all-day"


# ── Account resolution ─────────────────────────────────────────────


def test_resolve_calendar_accounts_picks_only_matching_kind(monkeypatch):
    from core.config import CONFIG

    accounts = {
        "work": {
            "email": "alex@example.com",
            "calendar": {
                "kind": "google-calendar",
                "include": ["primary"],
                "backfill_days": 30,
            },
        },
        "personal": {
            "email": "alex@gmail.com",
            "calendar": {"kind": "caldav-foo"},  # unknown kind → skipped
        },
        "no-calendar": {"email": "x@y.com"},
    }
    monkeypatch.setattr(CONFIG.personal, "accounts", accounts)

    out = cal._resolve_calendar_accounts()
    assert [a.account_id for a in out] == ["work"]
    assert out[0].backfill_days == 30
    assert out[0].include == ("primary",)


def test_resolve_calendar_accounts_falls_back_to_defaults(monkeypatch):
    from core.config import CONFIG

    accounts = {
        "work": {
            "email": "alex@example.com",
            "calendar": {"kind": "google-calendar"},
        },
    }
    monkeypatch.setattr(CONFIG.personal, "accounts", accounts)
    out = cal._resolve_calendar_accounts()
    assert out[0].backfill_days == CONFIG.limits.calendar_backfill_days
    assert out[0].future_days == CONFIG.limits.calendar_future_days
    assert out[0].max_per_run == CONFIG.limits.calendar_max_per_run
    assert out[0].include == ()


# ── Filtering helpers ──────────────────────────────────────────────


def test_is_holiday_matches_skip_keywords(monkeypatch):
    from core.config import CONFIG

    monkeypatch.setattr(CONFIG.personal, "calendar_skip_keywords", ["Weihnacht", "Easter"])
    assert cal._is_holiday("Easter Monday") is True
    assert cal._is_holiday("Weihnachten 1. Feiertag") is True
    assert cal._is_holiday("Sprint review") is False
    assert cal._is_holiday("") is False


def test_is_operator_declined_finds_self_attendee():
    ev = {
        "attendees": [
            {"email": "alex@example.com", "self": True, "responseStatus": "declined"},
            {"email": "other@example.com", "responseStatus": "accepted"},
        ],
    }
    assert cal._is_operator_declined(ev, "alex@example.com") is True


def test_is_operator_declined_accepts_when_no_decline():
    ev = {
        "attendees": [
            {"email": "alex@example.com", "self": True, "responseStatus": "accepted"},
        ],
    }
    assert cal._is_operator_declined(ev, "alex@example.com") is False
    assert cal._is_operator_declined({}, "alex@example.com") is False
    assert cal._is_operator_declined(ev, None) is False


# ── Calendar selection ────────────────────────────────────────────


def _account(**overrides) -> cal._CalendarAccount:
    base: dict[str, Any] = dict(
        account_id="work",
        include=(),
        backfill_days=90,
        future_days=7,
        since=None,
        max_per_run=500,
    )
    base.update(overrides)
    return cal._CalendarAccount(**base)


def test_select_calendars_explicit_include():
    cal_items = [
        {"id": "primary", "summary": "Personal", "primary": True, "selected": True},
        {"id": "work@example.com", "summary": "Work", "selected": True},
        {"id": "holidays@v.calendar.google.com", "summary": "DE Holidays", "selected": False},
    ]
    acct = _account(include=("Work",))
    sel = cal.CalendarCollector._select_calendars(cal_items, acct)
    assert [c["id"] for c in sel] == ["work@example.com"]


def test_select_calendars_defaults_to_selected():
    cal_items = [
        {"id": "primary", "summary": "Personal", "primary": True, "selected": True},
        {"id": "work@example.com", "summary": "Work", "selected": True},
        {"id": "holidays@v.calendar.google.com", "summary": "DE Holidays", "selected": False},
    ]
    acct = _account()
    sel = cal.CalendarCollector._select_calendars(cal_items, acct)
    assert {c["id"] for c in sel} == {"primary", "work@example.com"}


def test_select_calendars_falls_back_to_primary():
    cal_items = [
        {"id": "primary", "summary": "Personal", "primary": True, "selected": False},
        {"id": "other@example.com", "summary": "Other", "selected": False},
    ]
    sel = cal.CalendarCollector._select_calendars(cal_items, _account())
    assert [c["id"] for c in sel] == ["primary"]


# ── Rendering ─────────────────────────────────────────────────────


def _block(**overrides) -> cal._EventBlock:
    base: dict[str, Any] = dict(
        event_id="evt_abc",
        etag='"abc123"',
        start=datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 15, 9, 30, tzinfo=timezone.utc),
        all_day=False,
        summary="Standup",
        description="Daily team standup.",
        location="https://meet.google.com/abc",
        attendees=["bob@example.com", "jane@example.com"],
        organizer="alex@example.com",
        calendar_summary="Work",
        account_id="work",
        is_meeting=True,
        recurring_event_id=None,
        recurring_slug=None,
        recurring_title=None,
    )
    base.update(overrides)
    return cal._EventBlock(**base)


def test_render_event_block_contains_all_fields():
    block = _block()
    out = cal._render_event_block(block)
    assert out.startswith("## 09:00–09:30 · Standup")
    assert "- **Calendar:** Work (account: work)" in out
    assert "- **Attendees:** bob@example.com, jane@example.com" in out
    assert "- **Location:** https://meet.google.com/abc" in out
    assert "- **Event ID:** evt_abc" in out
    assert "Daily team standup." in out


def test_render_event_block_with_recurring_and_transcript():
    block = _block(
        recurring_event_id="rec_abc",
        recurring_slug="weekly-standup",
        recurring_title="Weekly Standup",
        transcript_link="[[../transcripts/gmeet/2026-05-15--standup--abc|gmeet]]",
    )
    out = cal._render_event_block(block)
    assert "- **Recurring:** [[concepts/weekly-standup|Weekly Standup]]" in out
    assert "- **Transcript:** [[../transcripts/gmeet/" in out


def test_render_date_file_frontmatter_and_managed_region():
    block = _block()
    md = cal._render_date_file("2026-05-15", [block], existing_text=None)
    assert md.startswith("---\n")
    assert "type: calendar-rollup" in md
    assert "date: '2026-05-15'" in md or "date: 2026-05-15" in md
    assert "event_count: 1" in md
    assert "meeting_hours: 0.5" in md
    assert cal._EVENTS_BEGIN in md
    assert cal._EVENTS_END in md
    assert "# Calendar — 2026-05-15" in md


def test_render_date_file_preserves_operator_prose():
    """Prose outside the managed region survives a regeneration."""
    block = _block()
    existing = (
        "---\nold: thing\n---\n"
        "# Calendar — 2026-05-15\n\n"
        "Operator note above the events.\n\n"
        f"{cal._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{cal._EVENTS_END}\n\n"
        "Operator note below the events.\n"
    )
    md = cal._render_date_file("2026-05-15", [block], existing_text=existing)
    assert "Operator note above the events." in md
    assert "Operator note below the events." in md
    assert "OLD EVENT" not in md  # managed region was rebuilt
    assert "Standup" in md


def test_render_date_file_single_managed_region():
    block = _block()
    md = cal._render_date_file("2026-05-15", [block], existing_text=None)
    assert md.count(cal._EVENTS_BEGIN) == 1
    assert md.count(cal._EVENTS_END) == 1


def test_render_date_file_round_trip_is_byte_stable(monkeypatch):
    """Regeneration must be a fixpoint: feeding a rendered file back as
    ``existing_text`` reproduces it byte-for-byte (operator vaults carry
    existing sentinel regions — the rewrite must never drift them)."""
    monkeypatch.setattr(cal, "now_iso", lambda: "2026-05-15T08:30:00Z")
    block = _block()
    existing = (
        "---\nold: thing\n---\n"
        "# Calendar — 2026-05-15\n\n"
        "Operator note above the events.\n\n"
        f"{cal._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{cal._EVENTS_END}\n\n"
        "Operator note below the events.\n"
    )
    once = cal._render_date_file("2026-05-15", [block], existing_text=existing)
    twice = cal._render_date_file("2026-05-15", [block], existing_text=once)
    assert twice == once


def test_split_operator_prose_stray_end_before_region():
    """A stray end marker BEFORE the genuine region must not blind the split
    (core.markers contract): the managed region is still located, so old
    event bodies never leak into the preserved operator prose."""
    body = (
        f"{cal._EVENTS_END}\n\n"
        "Operator note.\n\n"
        f"{cal._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{cal._EVENTS_END}\n\n"
        "Note below.\n"
    )
    pre, post = cal._split_operator_prose(f"# Calendar — 2026-05-15\n\n{body}")
    assert "## OLD EVENT" not in pre
    assert "## OLD EVENT" not in post
    assert "Note below." in post


# ── Transcript cross-link ──────────────────────────────────────────


def test_attach_transcript_links_matches_by_date_and_title():
    block = _block(
        summary="Alex × Sid",
        start=datetime(2026, 5, 14, 16, 0, tzinfo=timezone.utc),
    )
    ref = cal._TranscriptRef(
        relpath="raw/transcripts/jamie/2026-05-14--alex-x-sid--abc.md",
        title="Alex × Sid",
        title_slug=cal._slugify("Alex × Sid"),
        date_key="2026-05-14",
        kind="jamie",
    )
    n = cal._attach_transcript_links([block], [ref])
    assert n == 1
    assert block.transcript_link is not None
    assert "jamie" in block.transcript_link


def test_attach_transcript_links_ignores_other_dates():
    block = _block(summary="Standup")
    ref = cal._TranscriptRef(
        relpath="raw/transcripts/gmeet/2026-04-01--standup--xyz.md",
        title="Standup",
        title_slug="standup",
        date_key="2026-04-01",  # different date
        kind="gmeet",
    )
    n = cal._attach_transcript_links([block], [ref])
    assert n == 0
    assert block.transcript_link is None


def test_attach_transcript_links_substring_match():
    """A transcript title that is a substring of the event title still links.

    Real example: calendar event "Alex x Sid 1/3" + Jamie transcript whose
    Jamie-side title is just "Alex x Sid" (Jamie strips counter suffixes)."""
    block = _block(
        summary="Alex x Sid 1/3",
        start=datetime(2026, 5, 14, 16, 0, tzinfo=timezone.utc),
    )
    transcript_title = "Alex x Sid"
    ref = cal._TranscriptRef(
        relpath="raw/transcripts/jamie/2026-05-14--alex-x-sid--abc.md",
        title=transcript_title,
        title_slug=cal._slugify(transcript_title),
        date_key="2026-05-14",
        kind="jamie",
    )
    n = cal._attach_transcript_links([block], [ref])
    assert n == 1


# ── Bootstrap delegation ──────────────────────────────────────────


def test_calendar_auth_bootstrap_delegates(monkeypatch):
    seen = {}

    def fake_bootstrap(app, account_id):
        seen["scopes"] = app.scopes
        seen["account_id"] = account_id
        seen["bootstrap_cmd"] = app.bootstrap_cmd
        seen["service_label"] = app.service_label
        return True, "OK"

    monkeypatch.setattr(cal.google_oauth, "bootstrap", fake_bootstrap)
    ok, msg = cal.calendar_auth_bootstrap("work")
    assert ok is True
    assert msg == "OK"
    assert seen["account_id"] == "work"
    assert seen["bootstrap_cmd"] == "wiki calendar-auth"
    assert seen["service_label"] == "Google Calendar"
    assert seen["scopes"][0].endswith("/auth/calendar.readonly")


# ── Full run loop with a fake client ───────────────────────────────


class _FakeClient:
    """Stand-in for GoogleCalendarClient."""

    def __init__(self, cal_items: list[dict], events_by_cal: dict[str, list[dict]]):
        self._cal_items = cal_items
        self._events_by_cal = events_by_cal

    def list_calendars(self) -> list[dict]:
        return list(self._cal_items)

    def list_events(self, calendar_id: str, *, time_min=None, time_max=None,
                    updated_min=None, page_size=250, limit=None):
        for ev in self._events_by_cal.get(calendar_id, []):
            yield ev


@pytest.fixture
def _isolated_vault(monkeypatch, tmp_path):
    """Point ROOT_DIR + STATE_DIR + the calendar collector's module-level
    paths at a clean tmp_path so a real ``run()`` writes into the test
    sandbox, not the real vault."""
    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(core_paths, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cal, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(cal, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cal, "_STATE_FILE", tmp_path / "state" / "calendar-state.json")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "concepts").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _stub_session(monkeypatch, fake_client: _FakeClient):
    """Make `google_oauth.session()` return a sentinel; make the
    GoogleCalendarClient constructor return our fake."""
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: ("session-token", None))
    monkeypatch.setattr(
        cal,
        "GoogleCalendarClient",
        lambda session, timeout_s=30.0: fake_client,
    )


def _configure_one_account(monkeypatch, account_id="work", include=()):
    from core.config import CONFIG

    accounts = {
        account_id: {
            "email": "alex@example.com",
            "calendar": {
                "kind": "google-calendar",
                "include": list(include),
                "backfill_days": 30,
                "future_days": 7,
            },
        },
    }
    monkeypatch.setattr(CONFIG.personal, "accounts", accounts)


def test_run_writes_per_date_rollup(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "evt1",
                "etag": '"e1"',
                "summary": "Sprint review",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T10:00:00+00:00"},
                "attendees": [
                    {"email": "alex@example.com", "self": True, "responseStatus": "accepted"},
                    {"email": "bob@example.com", "responseStatus": "accepted"},
                ],
                "updated": "2026-05-15T08:00:00Z",
            },
            {
                "id": "evt2",
                "etag": '"e2"',
                "summary": "Focus block",
                "start": {"dateTime": "2026-05-15T10:30:00+00:00"},
                "end": {"dateTime": "2026-05-15T12:00:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)

    collector = cal.CalendarCollector()
    result = collector.run(dry_run=False, incremental=False)

    target = _isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md"
    assert target.exists(), f"expected {target} to be written; got: {result.message}"
    text = target.read_text(encoding="utf-8")
    assert "event_count: 2" in text
    assert "Sprint review" in text
    assert "Focus block" in text
    assert "bob@example.com" in text
    assert "evt1" in text and "evt2" in text


def test_run_skips_cancelled_and_declined(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "ok",
                "etag": '"1"',
                "summary": "Will land",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
            {
                "id": "cancelled",
                "etag": '"c"',
                "status": "cancelled",
                "summary": "Will not land",
                "start": {"dateTime": "2026-05-15T10:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T10:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
            {
                "id": "declined",
                "etag": '"d"',
                "summary": "Declined event",
                "start": {"dateTime": "2026-05-15T11:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T11:30:00+00:00"},
                "attendees": [
                    {"email": "alex@example.com", "self": True, "responseStatus": "declined"},
                ],
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run()

    target = _isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md"
    text = target.read_text(encoding="utf-8")
    assert "Will land" in text
    assert "Will not land" not in text
    assert "Declined event" not in text
    assert "event_count: 1" in text


def test_run_collapses_recurring_to_concept_page(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "evt-day1",
                "etag": '"e1"',
                "summary": "Weekly Standup",
                "recurringEventId": "rec-series-1",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
            {
                "id": "evt-day2",
                "etag": '"e2"',
                "summary": "Weekly Standup",
                "recurringEventId": "rec-series-1",
                "start": {"dateTime": "2026-05-16T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-16T09:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run()

    concept = _isolated_vault / "knowledge" / "concepts" / "weekly-standup.md"
    assert concept.exists()
    body = concept.read_text(encoding="utf-8")
    assert "type: concept" in body
    assert "series: true" in body

    rollup_a = (_isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md").read_text("utf-8")
    rollup_b = (_isolated_vault / "raw" / "notes" / "calendar" / "2026-05-16.md").read_text("utf-8")
    assert "[[concepts/weekly-standup|Weekly Standup]]" in rollup_a
    assert "[[concepts/weekly-standup|Weekly Standup]]" in rollup_b


def test_run_attaches_transcript_link(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)

    gmeet_dir = _isolated_vault / "raw" / "transcripts" / "gmeet"
    gmeet_dir.mkdir(parents=True)
    (gmeet_dir / "2026-05-15--sprint-review--abc.md").write_text(
        "---\n"
        "title: Sprint review\n"
        "type: transcript\n"
        "source: gmeet\n"
        "started_at: '2026-05-15T09:00:00Z'\n"
        "---\n\n## Summary\n\nbody\n",
        encoding="utf-8",
    )

    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "evt-x",
                "etag": '"x"',
                "summary": "Sprint review",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T10:00:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run()

    rollup = (_isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md").read_text("utf-8")
    assert "- **Transcript:** [[../transcripts/gmeet/" in rollup


def test_run_persists_state_per_account_and_calendar(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "evt1",
                "etag": '"e1"',
                "summary": "X",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run(incremental=True)

    state = json.loads(
        (_isolated_vault / "state" / "calendar-state.json").read_text(encoding="utf-8")
    )
    assert "work" in state
    cals = state["work"]["calendars"]
    assert "primary" in cals
    assert cals["primary"]["etags"]["evt1"] == '"e1"'
    assert cals["primary"]["watermark_updated"] == "2026-05-15T08:00:00Z"


def test_run_dry_run_writes_nothing(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={"primary": [
            {
                "id": "evt1",
                "etag": '"e1"',
                "summary": "X",
                "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                "updated": "2026-05-15T08:00:00Z",
            },
        ]},
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run(dry_run=True)
    target = _isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md"
    assert not target.exists()


def test_run_no_accounts_is_no_op(monkeypatch):
    from core.config import CONFIG

    monkeypatch.setattr(CONFIG.personal, "accounts", {})
    result = cal.CalendarCollector().run()
    assert "no calendar accounts configured" in result.message
