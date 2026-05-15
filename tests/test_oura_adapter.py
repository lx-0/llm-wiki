"""Adapter-unit tests for the Oura REST client.

Pure-parse tests against documented Oura v2 response shapes (verified
live 2026-05-15 against the operator's account):

- `/daily_sleep`     — daily SCORE only (5 keys: id, day, score, timestamp, contributors).
                       Sleep duration / HRV / HR live elsewhere — NOT here.
- `/daily_readiness` — daily readiness score + temperature deltas + contributors.
- `/daily_activity`  — daily steps + activity scores + duration breakdowns.
- `/sleep`           — session-level rows (potentially multiple per `day`:
                       long_sleep + naps). Carries `total_sleep_duration`,
                       `average_hrv`, `lowest_heart_rate`, `average_heart_rate`.
                       Adapter picks the longest-duration session per day to
                       extract overnight metrics.

Network is isolated via direct payload injection; no real PAT required.
"""
from __future__ import annotations

import pytest

from adapters.health.oura import (
    DailySummary,
    OuraAPIError,
    _parse_daily_sleep,
    _parse_daily_readiness,
    _parse_daily_activity,
    _parse_sleep_sessions,
    _merge_by_day,
)


# ── Response fixtures (shape verified live 2026-05-15) ───────────────


# `/daily_sleep` is JUST the score. No duration / HRV / HR fields here.
DAILY_SLEEP_PAYLOAD = {
    "data": [
        {
            "id": "abc-001",
            "day": "2026-05-14",
            "score": 84,
            "timestamp": "2026-05-14T07:00:00+00:00",
            "contributors": {
                "deep_sleep": 92,
                "efficiency": 90,
                "latency": 75,
                "rem_sleep": 80,
                "restfulness": 78,
                "timing": 88,
                "total_sleep": 86,
            },
        },
        {
            "id": "abc-002",
            "day": "2026-05-13",
            "score": 79,
            "timestamp": "2026-05-13T06:55:00+00:00",
            "contributors": {},
        },
    ],
    "next_token": None,
}


# `/sleep` is session-level — duration/HRV/HR live here. Multiple rows
# per `day` are normal (one long_sleep + zero-or-more naps).
SLEEP_SESSIONS_PAYLOAD = {
    "data": [
        # 2026-05-14: one long_sleep
        {
            "id": "ss-001",
            "day": "2026-05-14",
            "type": "long_sleep",
            "period": 0,
            "bedtime_start": "2026-05-13T23:30:00+00:00",
            "bedtime_end": "2026-05-14T06:48:00+00:00",
            "total_sleep_duration": 25920,    # 7.2 h
            "average_hrv": 52,
            "average_heart_rate": 58.2,
            "lowest_heart_rate": 54,
        },
        # 2026-05-13: long_sleep + a short nap. Adapter must pick the longer one.
        {
            "id": "ss-002",
            "day": "2026-05-13",
            "type": "late_nap",
            "period": 1,
            "total_sleep_duration": 1200,     # 20-min nap — shorter
            "average_hrv": 45,
            "average_heart_rate": 65.0,
            "lowest_heart_rate": 62,
        },
        {
            "id": "ss-003",
            "day": "2026-05-13",
            "type": "long_sleep",
            "period": 0,
            "total_sleep_duration": 23400,    # 6.5 h — the longer, correct one
            "average_hrv": 48,
            "average_heart_rate": 60.0,
            "lowest_heart_rate": 56,
        },
    ],
    "next_token": None,
}


READINESS_PAYLOAD = {
    "data": [
        {
            "id": "rdy-001",
            "day": "2026-05-14",
            "score": 79,
            "temperature_deviation": -0.15,
            "temperature_trend_deviation": 0.05,
            "timestamp": "2026-05-14T07:00:00+00:00",
            "contributors": {},
        },
        {
            "id": "rdy-002",
            "day": "2026-05-13",
            "score": 71,
            "timestamp": "2026-05-13T06:55:00+00:00",
            "contributors": {},
        },
    ],
    "next_token": None,
}


ACTIVITY_PAYLOAD = {
    "data": [
        {
            "id": "act-001",
            "day": "2026-05-14",
            "steps": 8412,
            "score": 76,
            "active_calories": 412,
            "total_calories": 2451,
            "timestamp": "2026-05-14T04:00:00+00:00",
        },
        {
            "id": "act-002",
            "day": "2026-05-13",
            "steps": 5021,
            "score": 64,
            "timestamp": "2026-05-13T04:00:00+00:00",
        },
    ],
    "next_token": None,
}


# ── _parse_daily_sleep — score-only ──────────────────────────────────


def test_parse_daily_sleep_extracts_score_only() -> None:
    """daily_sleep has score + day; everything else lives on /sleep sessions."""
    out = _parse_daily_sleep(DAILY_SLEEP_PAYLOAD)
    assert set(out.keys()) == {"2026-05-14", "2026-05-13"}
    assert out["2026-05-14"]["sleep_score"] == 84
    assert out["2026-05-13"]["sleep_score"] == 79
    # No other fields on this endpoint — the parser must NOT invent them.
    assert set(out["2026-05-14"].keys()) == {"sleep_score"}


def test_parse_daily_sleep_skips_rows_without_day() -> None:
    payload = {"data": [{"day": "2026-05-14", "score": 84}, {"score": 70}]}
    out = _parse_daily_sleep(payload)
    assert set(out.keys()) == {"2026-05-14"}


def test_parse_daily_sleep_handles_missing_score() -> None:
    payload = {"data": [{"day": "2026-05-14"}]}
    out = _parse_daily_sleep(payload)
    assert out["2026-05-14"]["sleep_score"] is None


def test_parse_daily_sleep_returns_empty_on_no_data() -> None:
    assert _parse_daily_sleep({"data": [], "next_token": None}) == {}
    assert _parse_daily_sleep({"data": None}) == {}
    assert _parse_daily_sleep({}) == {}


# ── _parse_sleep_sessions — picks longest session per day ────────────


def test_parse_sleep_sessions_extracts_metrics_from_longest_session_per_day() -> None:
    out = _parse_sleep_sessions(SLEEP_SESSIONS_PAYLOAD)
    # 2026-05-14: only one session — picked directly.
    may_14 = out["2026-05-14"]
    assert may_14["sleep_hours"] == pytest.approx(7.2, rel=1e-3)
    assert may_14["hrv_overnight"] == 52
    assert may_14["resting_hr"] == 54
    # 2026-05-13: long_sleep + nap. Adapter must pick the longer one
    # (23400s long_sleep, NOT the 1200s nap).
    may_13 = out["2026-05-13"]
    assert may_13["sleep_hours"] == pytest.approx(6.5, rel=1e-3)
    assert may_13["hrv_overnight"] == 48
    assert may_13["resting_hr"] == 56  # from long_sleep, not the 62 from the nap


def test_parse_sleep_sessions_tolerates_missing_optional_fields() -> None:
    payload = {"data": [{"day": "2026-05-14", "total_sleep_duration": 25920}]}
    out = _parse_sleep_sessions(payload)
    assert out["2026-05-14"]["sleep_hours"] == pytest.approx(7.2, rel=1e-3)
    assert out["2026-05-14"]["hrv_overnight"] is None
    assert out["2026-05-14"]["resting_hr"] is None


def test_parse_sleep_sessions_skips_rows_without_day_or_duration() -> None:
    payload = {
        "data": [
            {"day": "2026-05-14", "total_sleep_duration": 25920},
            {"total_sleep_duration": 5000},        # no day — drop
            {"day": "2026-05-13"},                  # no duration — drop
        ]
    }
    out = _parse_sleep_sessions(payload)
    assert set(out.keys()) == {"2026-05-14"}


def test_parse_sleep_sessions_returns_empty_on_no_data() -> None:
    assert _parse_sleep_sessions({"data": []}) == {}
    assert _parse_sleep_sessions({}) == {}


def test_parse_sleep_sessions_falls_back_to_average_hr_when_lowest_missing() -> None:
    """Older API responses may emit `average_heart_rate` only. Use that as a fallback."""
    payload = {
        "data": [{
            "day": "2026-05-14",
            "total_sleep_duration": 25920,
            "average_heart_rate": 58.2,
            # lowest_heart_rate absent
        }]
    }
    out = _parse_sleep_sessions(payload)
    assert out["2026-05-14"]["resting_hr"] == 58  # int-cast of average


# ── _parse_daily_readiness ───────────────────────────────────────────


def test_parse_readiness_extracts_score_per_day() -> None:
    out = _parse_daily_readiness(READINESS_PAYLOAD)
    assert out["2026-05-14"]["readiness_score"] == 79
    assert out["2026-05-13"]["readiness_score"] == 71


def test_parse_readiness_returns_empty_on_no_data() -> None:
    assert _parse_daily_readiness({"data": []}) == {}


# ── _parse_daily_activity ────────────────────────────────────────────


def test_parse_activity_extracts_steps_per_day() -> None:
    out = _parse_daily_activity(ACTIVITY_PAYLOAD)
    assert out["2026-05-14"]["steps"] == 8412
    assert out["2026-05-13"]["steps"] == 5021


def test_parse_activity_tolerates_missing_steps() -> None:
    payload = {"data": [{"day": "2026-05-14", "score": 76}]}
    out = _parse_daily_activity(payload)
    assert out["2026-05-14"]["steps"] is None


# ── _merge_by_day (four sources) ─────────────────────────────────────


def test_merge_by_day_combines_four_endpoints_into_one_summary_per_day() -> None:
    sleep = _parse_daily_sleep(DAILY_SLEEP_PAYLOAD)
    sessions = _parse_sleep_sessions(SLEEP_SESSIONS_PAYLOAD)
    readiness = _parse_daily_readiness(READINESS_PAYLOAD)
    activity = _parse_daily_activity(ACTIVITY_PAYLOAD)

    summaries = _merge_by_day(sleep, sessions, readiness, activity)
    by_day = {s.day: s for s in summaries}

    assert set(by_day.keys()) == {"2026-05-14", "2026-05-13"}
    may_14 = by_day["2026-05-14"]
    assert may_14.sleep_score == 84              # /daily_sleep
    assert may_14.sleep_hours == pytest.approx(7.2, rel=1e-3)  # /sleep
    assert may_14.hrv_overnight == 52            # /sleep
    assert may_14.resting_hr == 54               # /sleep
    assert may_14.readiness_score == 79          # /daily_readiness
    assert may_14.steps == 8412                  # /daily_activity


def test_merge_by_day_yields_summary_for_each_day_in_any_source() -> None:
    sleep = {"2026-05-14": {"sleep_score": 84}}
    sessions = {"2026-05-14": {"sleep_hours": 7.2, "hrv_overnight": 52, "resting_hr": 54}}
    readiness = {"2026-05-14": {"readiness_score": 79}}
    activity = {"2026-05-14": {"steps": 8412}, "2026-05-12": {"steps": 6000}}

    summaries = _merge_by_day(sleep, sessions, readiness, activity)
    by_day = {s.day: s for s in summaries}

    assert set(by_day.keys()) == {"2026-05-14", "2026-05-12"}
    may_12 = by_day["2026-05-12"]
    assert may_12.steps == 6000
    assert may_12.sleep_score is None
    assert may_12.sleep_hours is None


def test_merge_by_day_skips_days_with_only_None_metrics() -> None:
    sleep = {"2026-05-14": {"sleep_score": None}}
    sessions = {"2026-05-14": {"sleep_hours": None, "hrv_overnight": None, "resting_hr": None}}
    readiness = {"2026-05-14": {"readiness_score": None}}
    activity = {"2026-05-14": {"steps": None}}
    assert _merge_by_day(sleep, sessions, readiness, activity) == []


def test_merge_by_day_returns_results_sorted_by_day_ascending() -> None:
    sleep = {"2026-05-10": {"sleep_score": 70}, "2026-05-14": {"sleep_score": 84}}
    summaries = _merge_by_day(sleep, {}, {}, {})
    assert [s.day for s in summaries] == ["2026-05-10", "2026-05-14"]


# ── DailySummary defaults ────────────────────────────────────────────


def test_daily_summary_all_fields_default_none() -> None:
    s = DailySummary(day="2026-05-14")
    assert s.sleep_hours is None
    assert s.sleep_score is None
    assert s.readiness_score is None
    assert s.hrv_overnight is None
    assert s.steps is None
    assert s.resting_hr is None


def test_daily_summary_is_empty_when_all_metrics_none() -> None:
    s = DailySummary(day="2026-05-14")
    assert s.is_empty()
    s.sleep_score = 84
    assert not s.is_empty()


# ── OuraAPIError is a RuntimeError subclass ──────────────────────────


def test_oura_api_error_subclasses_runtime_error() -> None:
    assert issubclass(OuraAPIError, RuntimeError)
