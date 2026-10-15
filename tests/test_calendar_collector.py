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
  persists the recurring-series map.
- Rollup completeness: a date is rewritten only from a listing that holds
  every one of its events (whole window, edge days read whole, one block per
  event id, no rewrite after a failed / capped / one-account listing).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from collectors import calendar_collector as cal
from collectors import calendar_render as render
from core.utils import slugify

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
    start = datetime(2026, 5, 15, 9, 0, tzinfo=UTC)
    end = datetime(2026, 5, 15, 9, 30, tzinfo=UTC)
    assert render._format_event_window(start, end, all_day=False) == "09:00–09:30"


def test_format_event_window_all_day():
    start = datetime(2026, 5, 15, tzinfo=UTC)
    assert render._format_event_window(start, None, all_day=True) == "all-day"


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


def _block(**overrides) -> render._EventBlock:
    base: dict[str, Any] = dict(
        event_id="evt_abc",
        start=datetime(2026, 5, 15, 9, 0, tzinfo=UTC),
        end=datetime(2026, 5, 15, 9, 30, tzinfo=UTC),
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
    return render._EventBlock(**base)


def test_render_event_block_contains_all_fields():
    block = _block()
    out = render._render_event_block(block)
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
    out = render._render_event_block(block)
    assert "- **Recurring:** [[concepts/weekly-standup|Weekly Standup]]" in out
    assert "- **Transcript:** [[../transcripts/gmeet/" in out


def test_render_date_file_frontmatter_and_managed_region():
    block = _block()
    md = render._render_date_file("2026-05-15", [block], existing_text=None)
    assert md.startswith("---\n")
    assert "type: calendar-rollup" in md
    assert "date: '2026-05-15'" in md or "date: 2026-05-15" in md
    assert "event_count: 1" in md
    assert "meeting_hours: 0.5" in md
    assert render._EVENTS_BEGIN in md
    assert render._EVENTS_END in md
    assert "# Calendar — 2026-05-15" in md


def test_render_date_file_preserves_operator_prose():
    """Prose outside the managed region survives a regeneration."""
    block = _block()
    existing = (
        "---\nold: thing\n---\n"
        "# Calendar — 2026-05-15\n\n"
        "Operator note above the events.\n\n"
        f"{render._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{render._EVENTS_END}\n\n"
        "Operator note below the events.\n"
    )
    md = render._render_date_file("2026-05-15", [block], existing_text=existing)
    assert "Operator note above the events." in md
    assert "Operator note below the events." in md
    assert "OLD EVENT" not in md  # managed region was rebuilt
    assert "Standup" in md


def test_render_date_file_single_managed_region():
    block = _block()
    md = render._render_date_file("2026-05-15", [block], existing_text=None)
    assert md.count(render._EVENTS_BEGIN) == 1
    assert md.count(render._EVENTS_END) == 1


def test_render_date_file_round_trip_is_byte_stable(monkeypatch):
    """Regeneration must be a fixpoint: feeding a rendered file back as
    ``existing_text`` reproduces it byte-for-byte (operator vaults carry
    existing sentinel regions — the rewrite must never drift them)."""
    monkeypatch.setattr(render, "now_iso", lambda: "2026-05-15T08:30:00Z")
    block = _block()
    existing = (
        "---\nold: thing\n---\n"
        "# Calendar — 2026-05-15\n\n"
        "Operator note above the events.\n\n"
        f"{render._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{render._EVENTS_END}\n\n"
        "Operator note below the events.\n"
    )
    once = render._render_date_file("2026-05-15", [block], existing_text=existing)
    twice = render._render_date_file("2026-05-15", [block], existing_text=once)
    assert twice == once


def test_split_operator_prose_stray_end_before_region():
    """A stray end marker BEFORE the genuine region must not blind the split
    (core.markers contract): the managed region is still located, so old
    event bodies never leak into the preserved operator prose."""
    body = (
        f"{render._EVENTS_END}\n\n"
        "Operator note.\n\n"
        f"{render._EVENTS_BEGIN}\n\n## OLD EVENT\n\n{render._EVENTS_END}\n\n"
        "Note below.\n"
    )
    pre, post = render._split_operator_prose(f"# Calendar — 2026-05-15\n\n{body}")
    assert "## OLD EVENT" not in pre
    assert "## OLD EVENT" not in post
    assert "Note below." in post


# ── Transcript cross-link ──────────────────────────────────────────


def test_attach_transcript_links_matches_by_date_and_title():
    block = _block(
        summary="Alex × Sid",
        start=datetime(2026, 5, 14, 16, 0, tzinfo=UTC),
    )
    ref = cal._TranscriptRef(
        relpath="raw/transcripts/jamie/2026-05-14--alex-x-sid--abc.md",
        title="Alex × Sid",
        title_slug=slugify("Alex × Sid", max_len=60, ascii_only=True),
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
        start=datetime(2026, 5, 14, 16, 0, tzinfo=UTC),
    )
    transcript_title = "Alex x Sid"
    ref = cal._TranscriptRef(
        relpath="raw/transcripts/jamie/2026-05-14--alex-x-sid--abc.md",
        title=transcript_title,
        title_slug=slugify(transcript_title, max_len=60, ascii_only=True),
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

    def list_events(
        self,
        calendar_id: str,
        *,
        time_min=None,
        time_max=None,
        updated_min=None,
        page_size=250,
        limit=None,
    ):
        yield from self._events_by_cal.get(calendar_id, [])


_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


class _FrozenDatetime(datetime):
    """The collector's clock, pinned to `_NOW`: the fixtures' events sit inside
    its window (backfill 30 days, future 7)."""

    @classmethod
    def now(cls, tz=None):
        return _NOW.astimezone(tz) if tz is not None else _NOW.replace(tzinfo=None)


@pytest.fixture
def _isolated_vault(monkeypatch, tmp_path):
    """Point ROOT_DIR + STATE_DIR + the calendar collector's module-level
    paths at a clean tmp_path so a real ``run()`` writes into the test
    sandbox, not the real vault — with the collector's clock at `_NOW`."""
    from core import paths as core_paths

    monkeypatch.setattr(cal, "datetime", _FrozenDatetime)
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
        events_by_cal={
            "primary": [
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
            ]
        },
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
        events_by_cal={
            "primary": [
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
            ]
        },
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
        events_by_cal={
            "primary": [
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
            ]
        },
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
        events_by_cal={
            "primary": [
                {
                    "id": "evt-x",
                    "etag": '"x"',
                    "summary": "Sprint review",
                    "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                    "end": {"dateTime": "2026-05-15T10:00:00+00:00"},
                    "updated": "2026-05-15T08:00:00Z",
                },
            ]
        },
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run()

    rollup = (_isolated_vault / "raw" / "notes" / "calendar" / "2026-05-15.md").read_text("utf-8")
    assert "- **Transcript:** [[../transcripts/gmeet/" in rollup


def test_run_persists_the_recurring_map_and_drops_the_delta_cache(monkeypatch, _isolated_vault):
    """The state keeps the series → concept-slug map; the per-calendar
    watermark + etag cache of the retired delta sync leaves on the next run."""
    _configure_one_account(monkeypatch)
    state_file = _isolated_vault / "state" / "calendar-state.json"
    state_file.write_text(
        json.dumps(
            {
                "work": {
                    "calendars": {
                        "primary": {"watermark_updated": "2026-05-01T00:00:00Z", "etags": {}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={
            "primary": [
                {
                    "id": "evt1",
                    "summary": "Weekly Sync",
                    "recurringEventId": "rec-9",
                    "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                    "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                    "updated": "2026-05-15T08:00:00Z",
                },
            ]
        },
    )
    _stub_session(monkeypatch, fake)
    cal.CalendarCollector().run(incremental=True)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state == {"work": {"recurring": {"rec-9": "weekly-sync"}}}


def test_run_dry_run_writes_nothing(monkeypatch, _isolated_vault):
    _configure_one_account(monkeypatch)
    fake = _FakeClient(
        cal_items=[{"id": "primary", "summary": "Personal", "primary": True, "selected": True}],
        events_by_cal={
            "primary": [
                {
                    "id": "evt1",
                    "etag": '"e1"',
                    "summary": "X",
                    "start": {"dateTime": "2026-05-15T09:00:00+00:00"},
                    "end": {"dateTime": "2026-05-15T09:30:00+00:00"},
                    "updated": "2026-05-15T08:00:00Z",
                },
            ]
        },
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


# ── Rollup completeness: a date is rewritten only from all of its events ──
#
# The incremental run fetched only the events updated since a watermark and
# rewrote every touched date from those alone, so each unchanged event of that
# date vanished (lxw 2026-06-11: event_count 6 → 1, vault commit 2869a316).
# These tests drive run() through a fake that behaves like the Calendar API.

_PRIMARY = {"id": "primary", "summary": "Personal", "primary": True, "selected": True}
_WORK = {"id": "work-cal", "summary": "Work", "selected": True}


def _ev(eid, day, hh, *, updated="2026-05-01T00:00:00Z", status="confirmed", summary=None):
    start = datetime.fromisoformat(f"{day}T{hh}:00+00:00")
    return {
        "id": eid,
        "etag": f'"{eid}"',
        "status": status,
        "summary": summary or eid,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(minutes=30)).isoformat()},
        "updated": updated,
    }


class _ApiFake:
    """GoogleCalendarClient as the API behaves: events that overlap
    [time_min, time_max) in start order; with `updated_min` only the entries
    updated since then, cancelled ones included (showDeleted=false otherwise
    hides them); `limit` caps the listing; calendars in `fail` raise."""

    def __init__(self, cal_items, events_by_cal):
        self._cal_items = list(cal_items)
        self.events_by_cal = events_by_cal
        self.fail: set[str] = set()

    def list_calendars(self):
        return list(self._cal_items)

    def list_events(
        self,
        calendar_id,
        *,
        time_min=None,
        time_max=None,
        updated_min=None,
        page_size=250,
        limit=None,
    ):
        if calendar_id in self.fail:
            raise cal.CalendarAPIError("rate limited")
        lo = datetime.fromisoformat(time_min.replace("Z", "+00:00")) if time_min else None
        hi = datetime.fromisoformat(time_max.replace("Z", "+00:00")) if time_max else None
        out = []
        for ev in sorted(
            self.events_by_cal.get(calendar_id, []), key=lambda e: e["start"]["dateTime"]
        ):
            start = datetime.fromisoformat(ev["start"]["dateTime"])
            end = datetime.fromisoformat(ev["end"]["dateTime"])
            if (lo and end <= lo) or (hi and start >= hi):
                continue
            if updated_min is not None:
                if ev["updated"] < updated_min:
                    continue
            elif ev["status"] == "cancelled":
                continue
            out.append(ev)
        yield from out[:limit] if limit is not None else out


def _calendar_account(**overrides) -> dict:
    return {
        "email": "alex@example.com",
        "calendar": {
            "kind": "google-calendar",
            "include": [],
            "backfill_days": 30,
            "future_days": 7,
            **overrides,
        },
    }


def _accounts(monkeypatch, fakes: dict[str, _ApiFake], **overrides) -> None:
    """One calendar account per entry of `fakes`, each session served by its own fake."""
    from core.config import CONFIG

    monkeypatch.setattr(
        CONFIG.personal, "accounts", {aid: _calendar_account(**overrides) for aid in fakes}
    )
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: (aid, None))
    monkeypatch.setattr(cal, "GoogleCalendarClient", lambda session, timeout_s=30.0: fakes[session])


def _rollup(vault, day: str):
    return vault / "raw" / "notes" / "calendar" / f"{day}.md"


def _event_ids(path) -> list[str]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1]).get("event_ids", [])


def test_incremental_run_keeps_the_unchanged_events_of_a_touched_date(monkeypatch, _isolated_vault):
    events = [
        _ev("a", "2026-05-14", "09:00"),
        _ev("b", "2026-05-14", "11:00"),
        _ev("c", "2026-05-14", "14:00", updated="2026-05-10T00:00:00Z"),
    ]
    _accounts(monkeypatch, {"work": _ApiFake([_PRIMARY], {"primary": events})})
    cal.CalendarCollector().run()

    events[2] = {**events[2], "summary": "Moved", "updated": "2026-05-15T10:00:00Z"}
    cal.CalendarCollector().run(incremental=True)

    path = _rollup(_isolated_vault, "2026-05-14")
    assert _event_ids(path) == ["a", "b", "c"]
    assert "Moved" in path.read_text(encoding="utf-8")


def test_a_cancelled_event_leaves_its_rollup(monkeypatch, _isolated_vault):
    events = [
        _ev("a", "2026-05-14", "09:00"),
        _ev("b", "2026-05-14", "11:00", updated="2026-05-02T00:00:00Z"),
        _ev("z", "2026-05-13", "10:00", updated="2026-05-02T00:00:00Z"),
    ]
    _accounts(monkeypatch, {"work": _ApiFake([_PRIMARY], {"primary": events})})
    cal.CalendarCollector().run()

    for i in (1, 2):
        events[i] = {**events[i], "status": "cancelled", "updated": "2026-05-15T10:00:00Z"}
    cal.CalendarCollector().run(incremental=True)

    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["a"]
    emptied = _rollup(_isolated_vault, "2026-05-13")
    assert _event_ids(emptied) == []
    assert "event_count: 0" in emptied.read_text(encoding="utf-8")


def test_the_same_event_in_two_calendars_is_rendered_once(monkeypatch, _isolated_vault):
    shared = _ev("s", "2026-05-14", "10:00")
    fake = _ApiFake([_PRIMARY, _WORK], {"primary": [shared], "work-cal": [dict(shared)]})
    _accounts(monkeypatch, {"work": fake})

    cal.CalendarCollector().run()

    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["s"]


def test_rollups_are_left_alone_when_a_calendar_cannot_be_fetched(monkeypatch, _isolated_vault):
    fake = _ApiFake(
        [_PRIMARY, _WORK],
        {
            "primary": [_ev("p", "2026-05-14", "09:00")],
            "work-cal": [_ev("w", "2026-05-14", "10:00")],
        },
    )
    _accounts(monkeypatch, {"work": fake})
    cal.CalendarCollector().run()

    fake.fail = {"work-cal"}
    result = cal.CalendarCollector().run(incremental=True)

    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["p", "w"]
    assert "rollups not rewritten" in result.message


def test_the_oldest_date_of_the_window_is_read_whole(monkeypatch, _isolated_vault):
    """NOW is 12:00 and backfill 30 days: a window opening at now − 30 d sees
    only the afternoon of its first date."""
    events = [_ev("early", "2026-04-15", "09:00"), _ev("late", "2026-04-15", "15:00")]
    _accounts(monkeypatch, {"work": _ApiFake([_PRIMARY], {"primary": events})})

    cal.CalendarCollector().run()

    assert _event_ids(_rollup(_isolated_vault, "2026-04-15")) == ["early", "late"]


def test_dates_past_a_capped_listing_are_left_alone(monkeypatch, _isolated_vault):
    events = [
        _ev("x", "2026-05-13", "09:00"),
        _ev("y1", "2026-05-14", "09:00"),
        _ev("y2", "2026-05-14", "11:00"),
    ]
    fake = _ApiFake([_PRIMARY], {"primary": events})
    _accounts(monkeypatch, {"work": fake})
    cal.CalendarCollector().run()

    _accounts(monkeypatch, {"work": fake}, max_per_run=2)  # the listing now stops inside 05-14
    cal.CalendarCollector().run(incremental=True)

    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["y1", "y2"]


def test_an_unchanged_rollup_is_not_rewritten(monkeypatch, _isolated_vault):
    events = [_ev("a", "2026-05-14", "09:00")]
    _accounts(monkeypatch, {"work": _ApiFake([_PRIMARY], {"primary": events})})
    cal.CalendarCollector().run()
    path = _rollup(_isolated_vault, "2026-05-14")
    first = path.read_text(encoding="utf-8")

    result = cal.CalendarCollector().run(incremental=True)

    assert path not in result.files_written
    assert path.read_text(encoding="utf-8") == first


def test_a_one_account_run_leaves_rollups_other_accounts_feed(monkeypatch, _isolated_vault):
    fakes = {
        "work": _ApiFake([_PRIMARY], {"primary": [_ev("w", "2026-05-14", "09:00")]}),
        "home": _ApiFake([_PRIMARY], {"primary": [_ev("h", "2026-05-14", "18:00")]}),
    }
    _accounts(monkeypatch, fakes)
    cal.CalendarCollector().run()
    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["w", "h"]

    cal.CalendarCollector().run(account="work")

    assert _event_ids(_rollup(_isolated_vault, "2026-05-14")) == ["w", "h"]
