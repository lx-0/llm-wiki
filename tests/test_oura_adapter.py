"""Adapter-unit tests for the Oura REST client.

Pure-parse tests against documented Oura v2 response shapes. Network is
isolated via httpx mocking; no real PAT required to run these.
"""
from __future__ import annotations

import pytest

from adapters.health.oura import (
    DailySummary,
    OuraAPIError,
    _parse_daily_sleep,
    _parse_daily_readiness,
    _parse_daily_activity,
    _merge_by_day,
)


# ── Response fixtures (shape from cloud.ouraring.com/v2 docs) ────────


# /v2/usercollection/daily_sleep — daily sleep *score* + contributors.
# The full sleep-session metrics (total_sleep_duration, average_hrv,
# average_heart_rate) live on /v2/usercollection/sleep, but `daily_sleep`
# also carries them at top level for the day's primary session in current
# API revisions. Parse defensively: pull whichever fields are present.
SLEEP_PAYLOAD = {
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
            "total_sleep_duration": 25920,
            "average_hrv": 52,
            "average_heart_rate": 54,
        },
        {
            "id": "abc-002",
            "day": "2026-05-13",
            "score": 79,
            "timestamp": "2026-05-13T06:55:00+00:00",
            "contributors": {},
            "total_sleep_duration": 23400,
            "average_hrv": 48,
            "average_heart_rate": 56,
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


# ── _parse_daily_sleep ───────────────────────────────────────────────


def test_parse_sleep_extracts_score_hours_hrv_and_hr_per_day() -> None:
    out = _parse_daily_sleep(SLEEP_PAYLOAD)
    assert set(out.keys()) == {"2026-05-14", "2026-05-13"}
    may_14 = out["2026-05-14"]
    assert may_14["sleep_score"] == 84
    assert may_14["sleep_hours"] == pytest.approx(25920 / 3600, rel=1e-3)  # 7.2 h
    assert may_14["hrv_overnight"] == 52
    assert may_14["resting_hr"] == 54


def test_parse_sleep_tolerates_missing_optional_fields() -> None:
    # A minimal Oura payload — only `day` + `score`, no session metrics.
    minimal = {"data": [{"day": "2026-05-14", "score": 80}], "next_token": None}
    out = _parse_daily_sleep(minimal)
    assert out["2026-05-14"]["sleep_score"] == 80
    # Missing fields stay None — never raise KeyError.
    assert out["2026-05-14"]["sleep_hours"] is None
    assert out["2026-05-14"]["hrv_overnight"] is None
    assert out["2026-05-14"]["resting_hr"] is None


def test_parse_sleep_skips_rows_without_day() -> None:
    # Oura occasionally emits rows lacking `day` (mid-session edge cases).
    payload = {
        "data": [
            {"day": "2026-05-14", "score": 84},
            {"score": 70},  # no day — drop
        ],
        "next_token": None,
    }
    out = _parse_daily_sleep(payload)
    assert set(out.keys()) == {"2026-05-14"}


def test_parse_sleep_returns_empty_on_no_data() -> None:
    assert _parse_daily_sleep({"data": [], "next_token": None}) == {}
    assert _parse_daily_sleep({"data": None}) == {}
    assert _parse_daily_sleep({}) == {}


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


# ── _merge_by_day ────────────────────────────────────────────────────


def test_merge_by_day_combines_three_endpoints_into_one_summary_per_day() -> None:
    sleep = _parse_daily_sleep(SLEEP_PAYLOAD)
    readiness = _parse_daily_readiness(READINESS_PAYLOAD)
    activity = _parse_daily_activity(ACTIVITY_PAYLOAD)

    summaries = _merge_by_day(sleep, readiness, activity)
    by_day = {s.day: s for s in summaries}

    assert set(by_day.keys()) == {"2026-05-14", "2026-05-13"}
    may_14 = by_day["2026-05-14"]
    assert may_14.sleep_score == 84
    assert may_14.sleep_hours == pytest.approx(7.2, rel=1e-2)
    assert may_14.hrv_overnight == 52
    assert may_14.resting_hr == 54
    assert may_14.readiness_score == 79
    assert may_14.steps == 8412


def test_merge_by_day_yields_summary_for_each_day_present_in_any_source() -> None:
    # Day 2026-05-12 in activity-only — should still get a summary
    # with sleep/readiness fields None.
    sleep = {"2026-05-14": {"sleep_score": 84, "sleep_hours": 7.2, "hrv_overnight": 52, "resting_hr": 54}}
    readiness = {"2026-05-14": {"readiness_score": 79}}
    activity = {"2026-05-14": {"steps": 8412}, "2026-05-12": {"steps": 6000}}

    summaries = _merge_by_day(sleep, readiness, activity)
    by_day = {s.day: s for s in summaries}

    assert set(by_day.keys()) == {"2026-05-14", "2026-05-12"}
    may_12 = by_day["2026-05-12"]
    assert may_12.steps == 6000
    assert may_12.sleep_score is None
    assert may_12.readiness_score is None


def test_merge_by_day_skips_days_with_only_None_metrics() -> None:
    """A day where every metric is None contributes nothing (skip-empty rule)."""
    sleep = {"2026-05-14": {"sleep_score": None, "sleep_hours": None, "hrv_overnight": None, "resting_hr": None}}
    readiness = {"2026-05-14": {"readiness_score": None}}
    activity = {"2026-05-14": {"steps": None}}

    summaries = _merge_by_day(sleep, readiness, activity)
    assert summaries == []


def test_merge_by_day_returns_results_sorted_by_day_ascending() -> None:
    sleep = {"2026-05-10": {"sleep_score": 70}, "2026-05-14": {"sleep_score": 84}}
    summaries = _merge_by_day(sleep, {}, {})
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
    # Mirrors JamieAPIError — callers can catch (RuntimeError, OuraAPIError).
    assert issubclass(OuraAPIError, RuntimeError)
