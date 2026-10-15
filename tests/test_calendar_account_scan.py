"""M033-S04-T05 — characterisation of `CalendarCollector._run_one_account`, the
per-account scan, with a recording fake client: the per-calendar fetch arguments, the
etag / watermark state merge, the failure branches and the message — what the `run()`
tests in test_calendar_collector.py leave unpinned."""

from __future__ import annotations

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
    monkeypatch.setattr(cal, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(cal, "_STATE_FILE", tmp_path / "state" / "calendar-state.json")
    (tmp_path / "knowledge" / "concepts").mkdir(parents=True)
    return tmp_path


def _scan(monkeypatch, client, *, state=None, incremental=False, since=None):
    """One `google-calendar` account over the recording client; returns
    (collector, result, state) after the per-account scan."""
    from core.config import CONFIG

    block = {"kind": "google-calendar", "include": [], "backfill_days": 30, "future_days": 7}
    if since:
        block["since"] = since
    monkeypatch.setattr(
        CONFIG.personal, "accounts", {"work": {"email": "alex@example.com", "calendar": block}}
    )
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: ("session", None))
    monkeypatch.setattr(cal, "GoogleCalendarClient", lambda session, timeout_s=30.0: client)
    collector = cal.CalendarCollector()
    state = {} if state is None else state
    result = collector._run_one_account(
        collector._accounts[0], state=state, incremental=incremental
    )
    return collector, result, state


def test_plain_scan_message_payload_and_state_shape(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1, EVT2]})

    collector, (msg, (blocks, new_concepts), touched), state = _scan(monkeypatch, client)

    assert msg == "calendars=1 · listed=2 · blocks=2 · recurring=1"
    assert [b.summary for b in blocks] == ["Sprint review", "Weekly Standup"]
    assert blocks[0].attendees == ["bob@example.com"] and blocks[0].is_meeting is True
    assert blocks[1].recurring_slug == "weekly-standup"
    assert blocks[1].recurring_title == "Weekly Standup"
    assert new_concepts == [("weekly-standup", blocks[1])]
    assert touched is True
    assert state == {
        "work": {
            "calendars": {
                "primary": {
                    "etags": {"evt1": '"e1"', "evt2": '"e2"'},
                    "watermark_updated": "2026-05-15T08:00:00Z",
                }
            },
            "recurring": {"rec-1": "weekly-standup"},
        }
    }
    [call] = client.calls
    assert call["calendar_id"] == "primary"
    assert call["updated_min"] is None
    assert call["limit"] == collector._accounts[0].max_per_run
    assert call["time_min"].endswith("Z") and call["time_max"].endswith("Z")


def test_incremental_scan_uses_the_stored_watermark_and_unions_etags(monkeypatch, vault) -> None:
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
    assert call["updated_min"] == "2026-05-10T00:00:00Z"
    assert call["time_min"].endswith("Z")
    assert state["work"]["calendars"]["primary"] == {
        "etags": {"old": '"o"', "evt1": '"e1"'},
        "watermark_updated": "2026-05-15T08:00:00Z",
    }
    assert state["work"]["recurring"] == {}


def test_configured_since_sets_time_min_when_there_is_no_watermark(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]})

    _scan(monkeypatch, client, since="2026-01-01T00:00:00Z")

    [call] = client.calls
    assert call["time_min"] == "2026-01-01T00:00:00Z"
    assert call["updated_min"] is None


def test_failing_calendar_is_skipped_and_the_rest_scanned(monkeypatch, vault) -> None:
    client = _RecordingClient(
        [PRIMARY, WORK], {"primary": [EVT1], "work@example.com": [EVT2]}, fail={"primary"}
    )

    _collector, (msg, (blocks, _concepts), touched), state = _scan(monkeypatch, client)

    assert msg == "calendars=2 · listed=1 · blocks=1 · recurring=1"
    assert [b.summary for b in blocks] == ["Weekly Standup"] and touched is True
    assert [c["calendar_id"] for c in client.calls] == ["primary", "work@example.com"]
    assert set(state["work"]["calendars"]) == {"work@example.com"}


def test_list_calendars_failure_scans_nothing(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]}, fail_calendars=True)

    _collector, result, state = _scan(monkeypatch, client)

    assert result == ("list_calendars failed: boom", ([], []), False)
    assert client.calls == [] and state == {}


def test_no_calendars_selected_is_a_noop(monkeypatch, vault) -> None:
    client = _RecordingClient([], {})

    _collector, result, state = _scan(monkeypatch, client)

    assert result == ("no-op (no calendars selected)", ([], []), False)
    assert state == {}


def test_auth_failure_returns_before_listing(monkeypatch, vault) -> None:
    client = _RecordingClient([PRIMARY], {"primary": [EVT1]})
    from core.config import CONFIG

    block = {"kind": "google-calendar", "include": [], "backfill_days": 30, "future_days": 7}
    monkeypatch.setattr(
        CONFIG.personal, "accounts", {"work": {"email": "alex@example.com", "calendar": block}}
    )
    monkeypatch.setattr(cal.google_oauth, "session", lambda app, aid: (None, "no token"))
    monkeypatch.setattr(cal, "GoogleCalendarClient", lambda session, timeout_s=30.0: client)
    collector = cal.CalendarCollector()

    result = collector._run_one_account(collector._accounts[0], state={}, incremental=False)

    assert result == ("auth: no token", ([], []), False)
    assert client.calls == []
