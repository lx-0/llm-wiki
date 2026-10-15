"""M033-S04-T05 — characterisation of `CalendarCollector._run_one_account`, the
per-account scan, with a recording fake client: the per-calendar fetch arguments, the
coverage the scan vouches for, the account state, the failure branches and the message —
what the `run()` tests in test_calendar_collector.py leave unpinned.

Since M033-S05-T06 the scan lists the whole window on every run (no `updatedMin`, no
per-calendar watermark / etag cache): the delta listing rewrote each touched date from
its changed events alone and dropped the rest."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collectors import calendar_collector as cal

EVT1 = {
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
}
EVT2 = {
    "id": "evt2",
    "etag": '"e2"',
    "summary": "Weekly Standup",
    "recurringEventId": "rec-1",
    "start": {"dateTime": "2026-05-14T09:00:00+00:00"},
    "end": {"dateTime": "2026-05-14T09:30:00+00:00"},
    "updated": "2026-05-14T08:00:00Z",
}
PRIMARY = {"id": "primary", "summary": "Personal", "primary": True, "selected": True}
WORK = {"id": "work@example.com", "summary": "Work", "selected": True}

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
# backfill 30 / future 7 days from _NOW; the fetch reaches a day further each side.
FIRST, LAST = "2026-04-15", "2026-05-22"
TIME_MIN, TIME_MAX = "2026-04-14T00:00:00Z", "2026-05-24T00:00:00Z"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _NOW.astimezone(tz) if tz is not None else _NOW.replace(tzinfo=None)


class _RecordingClient:
    """Stand-in for GoogleCalendarClient: canned calendars + events, every
    `list_events` call recorded, a configurable failing calendar set."""

    def __init__(self, cal_items, events_by_cal, *, fail=(), fail_calendars=False):
        self._cal_items = list(cal_items)
        self._events_by_cal = dict(events_by_cal)
        self.fail = set(fail)
        self.fail_calendars = fail_calendars
        self.calls: list[dict] = []

    def list_calendars(self):
        if self.fail_calendars:
            raise cal.CalendarAPIError("boom")
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
        self.calls.append(
            {
                "calendar_id": calendar_id,
                "time_min": time_min,
                "time_max": time_max,
                "updated_min": updated_min,
                "limit": limit,
            }
        )
        if calendar_id in self.fail:
            raise cal.CalendarAPIError("rate limited")
        yield from self._events_by_cal.get(calendar_id, [])


@pytest.fixture
def vault(monkeypatch, tmp_path):
    monkeypatch.setattr(cal, "datetime", _FrozenDatetime)
    monkeypatch.setattr(cal, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(cal, "_STATE_FILE", tmp_path / "state" / "calendar-state.json")
    (tmp_path / "knowledge" / "concepts").mkdir(parents=True)
    return tmp_path


def _configure(monkeypatch, client, **block_overrides):
    from core.config import CONFIG

    block = {"kind": "google-calendar", "include": [], "backfill_days": 30, "future_days": 7}
    block.update(block_overrides)
    monkeypatch.setattr(
        CONFIG.personal, "accounts", {"work": {"email": "alex@example.com", "calendar": block}}
    )
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: ("session", None))
    monkeypatch.setattr(cal, "GoogleCalendarClient", lambda session, timeout_s=30.0: client)


def _scan(monkeypatch, client, *, state=None, incremental=False, **block_overrides):
    """One `google-calendar` account over the recording client; returns
    (collector, result, state) after the per-account scan."""
    _configure(monkeypatch, client, **block_overrides)
    collector = cal.CalendarCollector()
    state = {} if state is None else state
    result = collector._run_one_account(
        collector._accounts[0], state=state, incremental=incremental
    )
    return collector, result, state


def test_plain_scan_message_payload_and_state_shape(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1, EVT2]})

    collector, (msg, (blocks, new_concepts, coverage), touched), state = _scan(monkeypatch, client)

    assert msg == "calendars=1 · listed=2 · blocks=2 · recurring=1"
    assert [b.summary for b in blocks] == ["Sprint review", "Weekly Standup"]
    assert blocks[0].attendees == ["bob@example.com"] and blocks[0].is_meeting is True
    assert blocks[1].recurring_slug == "weekly-standup"
    assert blocks[1].recurring_title == "Weekly Standup"
    assert new_concepts == [("weekly-standup", blocks[1])]
    assert coverage == cal._Coverage("work", FIRST, LAST)
    assert touched is True  # the recurring map grew
    assert state == {"work": {"recurring": {"rec-1": "weekly-standup"}}}
    assert client.calls == [
        {
            "calendar_id": "primary",
            "time_min": TIME_MIN,
            "time_max": TIME_MAX,
            "updated_min": None,
            "limit": collector._accounts[0].max_per_run,
        }
    ]


def test_incremental_scan_lists_the_whole_window_and_drops_the_delta_cache(
    monkeypatch, vault
) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]})
    state = {
        "work": {
            "calendars": {
                "primary": {"watermark_updated": "2026-05-10T00:00:00Z", "etags": {"old": '"o"'}}
            }
        }
    }

    _collector, (msg, _payload, touched), state = _scan(
        monkeypatch, client, state=state, incremental=True
    )

    assert msg == "calendars=1 · listed=1 · blocks=1 · recurring=0" and touched is True
    [call] = client.calls
    assert call["updated_min"] is None
    assert (call["time_min"], call["time_max"]) == (TIME_MIN, TIME_MAX)
    assert state == {"work": {"recurring": {}}}


def test_an_unchanged_account_state_is_not_touched(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT2]})
    state = {"work": {"recurring": {"rec-1": "weekly-standup"}}}

    _collector, (_msg, _payload, touched), _state = _scan(monkeypatch, client, state=state)

    assert touched is False


def test_configured_since_widens_a_full_run_for_every_calendar(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY, WORK], {"primary": [EVT1], "work@example.com": [EVT2]})

    _collector, (_m, (_b, _c, coverage), _t), _s = _scan(
        monkeypatch, client, since="2026-01-01T00:00:00Z"
    )
    _scan(monkeypatch, client, incremental=True, since="2026-01-01T00:00:00Z")

    assert [c["time_min"] for c in client.calls] == [
        "2025-12-31T00:00:00Z",
        "2025-12-31T00:00:00Z",
        TIME_MIN,
        TIME_MIN,
    ]
    assert coverage.first == "2026-01-01"


def test_failing_calendar_is_skipped_and_the_scan_marked_incomplete(monkeypatch, vault) -> None:
    client = _RecordingClient(
        [PRIMARY, WORK], {"primary": [EVT1], "work@example.com": [EVT2]}, fail={"primary"}
    )

    _collector, (msg, (blocks, _concepts, coverage), touched), _state = _scan(monkeypatch, client)

    assert msg == "calendars=2 · listed=1 · blocks=1 · recurring=1"
    assert [b.summary for b in blocks] == ["Weekly Standup"] and touched is True
    assert [c["calendar_id"] for c in client.calls] == ["primary", "work@example.com"]
    assert coverage.complete is False


def test_a_capped_listing_records_the_date_it_stopped_in(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT2, EVT1]})  # in start order

    _collector, (_msg, (_blocks, _concepts, coverage), _t), _s = _scan(
        monkeypatch, client, max_per_run=2
    )

    assert coverage.complete is True and coverage.cut == "2026-05-15"


def test_list_calendars_failure_scans_nothing(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]}, fail_calendars=True)

    _collector, result, state = _scan(monkeypatch, client)

    partial = cal._Coverage("work", FIRST, LAST, complete=False)
    assert result == ("list_calendars failed: boom", ([], [], partial), False)
    assert client.calls == [] and state == {}


def test_no_calendars_selected_is_a_noop(monkeypatch, vault) -> None:
    client = _RecordingClient([], {})

    _collector, result, state = _scan(monkeypatch, client)

    assert result == (
        "no-op (no calendars selected)",
        ([], [], cal._Coverage("work", FIRST, LAST)),
        False,
    )
    assert state == {}


def test_auth_failure_returns_before_listing(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]})
    _configure(monkeypatch, client)
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: (None, "no token"))
    collector = cal.CalendarCollector()

    result = collector._run_one_account(collector._accounts[0], state={}, incremental=False)

    partial = cal._Coverage("work", FIRST, LAST, complete=False)
    assert result == ("auth: no token", ([], [], partial), False)
    assert client.calls == []
