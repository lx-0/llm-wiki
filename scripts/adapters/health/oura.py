"""Oura REST client + daily-summary parsing.

Wire shape (cloud.ouraring.com/v2, Bearer PAT — verified live 2026-05-15):

    base    https://api.ouraring.com/v2/usercollection
    auth    Authorization: Bearer <pat>
    endpoints used (Phase 1):
      /daily_sleep?start_date=&end_date=      — daily SCORE ONLY (5-key row)
      /daily_readiness?start_date=&end_date=  — daily readiness score + temp deltas
      /daily_activity?start_date=&end_date=   — daily steps + activity scores
      /sleep?start_date=&end_date=            — session-level rows (long_sleep + naps)
    response  {"data": [{...row...}], "next_token": null | "<cursor>"}

`/daily_sleep` carries ONLY the score (id, day, score, timestamp,
contributors). The session-level metrics (`total_sleep_duration`,
`average_hrv`, `lowest_heart_rate`) live on `/sleep` instead, where
multiple rows per day are normal (one `long_sleep` + zero-or-more naps).
The adapter picks the longest-duration session per day to extract
overnight metrics — naps don't contribute to "resting" baselines.

`_parse_*` helpers are pure — tested in isolation. The OuraClient is a
thin httpx shell around them with retry + auth + pagination.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)


# ── API constants ───────────────────────────────────────────────────

_BASE_URL = "https://api.ouraring.com/v2/usercollection"
_USER_AGENT = "llm-wiki/oura-adapter"
_PAGE_SIZE_HINT = 200  # Oura allows up to ~250; 200 leaves headroom


class OuraAPIError(RuntimeError):
    """Raised on non-recoverable Oura API failures (401, persistent 5xx, schema)."""


# ── Daily summary ────────────────────────────────────────────────────


@dataclass
class DailySummary:
    """One merged-by-day record across daily_sleep / daily_readiness / daily_activity.

    Field semantics (Phase 1 — Oura only):
    - `sleep_hours`: total sleep duration in hours (from `total_sleep_duration` seconds).
    - `sleep_score`: daily_sleep `score` (0-100, Oura's composite).
    - `readiness_score`: daily_readiness `score` (0-100).
    - `hrv_overnight`: average HRV during sleep (ms).
    - `steps`: daily_activity `steps`.
    - `resting_hr`: average heart rate during sleep (bpm).

    HealthKit-sourced fields (`weight_kg`, etc.) are added in Phase 2 — left
    out of the Phase 1 shape entirely to avoid empty-field noise in the
    rendered frontmatter.
    """

    day: str  # YYYY-MM-DD
    sleep_hours: float | None = None
    sleep_score: int | None = None
    readiness_score: int | None = None
    hrv_overnight: int | None = None
    steps: int | None = None
    resting_hr: int | None = None

    def is_empty(self) -> bool:
        """True when every metric is None — the collector skips writing the file."""
        return all(
            getattr(self, f) is None
            for f in (
                "sleep_hours",
                "sleep_score",
                "readiness_score",
                "hrv_overnight",
                "steps",
                "resting_hr",
            )
        )


# ── Parsers (pure — TDD'd) ───────────────────────────────────────────


def _iter_rows(payload: Any) -> list[dict]:
    """Defensive accessor — Oura wraps under `data: [...]` but may emit None."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def _parse_daily_sleep(payload: Any) -> dict[str, dict]:
    """Extract per-day {sleep_score}.

    `/daily_sleep` rows carry ONLY the score (verified live 2026-05-15).
    Duration / HRV / heart rate live on `/sleep` — see `_parse_sleep_sessions`.
    """
    out: dict[str, dict] = {}
    for row in _iter_rows(payload):
        day = row.get("day")
        if not isinstance(day, str) or not day:
            continue
        score = row.get("score")
        out[day] = {
            "sleep_score": int(score) if isinstance(score, (int, float)) else None,
        }
    return out


def _parse_sleep_sessions(payload: Any) -> dict[str, dict]:
    """Extract per-day {sleep_hours, hrv_overnight, resting_hr} from /sleep.

    `/sleep` returns session-level rows — potentially multiple per `day`:
    one `long_sleep` plus zero-or-more `late_nap` / `short_nap` rows.
    We pick the longest-duration session per day; naps don't contribute
    to overnight baselines (the operator's resting metrics).

    `resting_hr` uses `lowest_heart_rate` (the minimum observed during the
    session — standard fitness-app definition of "resting"). Falls back to
    `average_heart_rate` when `lowest_heart_rate` is missing.

    Rows without `day` or without `total_sleep_duration` are dropped —
    no duration means we can't pick a "longest" session for that day.
    """
    # group rows by day, retain the one with max duration
    longest_per_day: dict[str, dict] = {}
    for row in _iter_rows(payload):
        day = row.get("day")
        if not isinstance(day, str) or not day:
            continue
        duration_s = row.get("total_sleep_duration")
        if not isinstance(duration_s, (int, float)) or duration_s <= 0:
            continue
        existing = longest_per_day.get(day)
        if existing is None or duration_s > existing.get("total_sleep_duration", 0):
            longest_per_day[day] = row

    out: dict[str, dict] = {}
    for day, row in longest_per_day.items():
        duration_s = row["total_sleep_duration"]
        hrv = row.get("average_hrv")
        # `resting_hr` = lowest_heart_rate when present, else average_heart_rate.
        # Both standard fitness conventions; either is more useful than nothing.
        lowest = row.get("lowest_heart_rate")
        avg_hr = row.get("average_heart_rate")
        if isinstance(lowest, (int, float)):
            resting_hr: int | None = int(lowest)
        elif isinstance(avg_hr, (int, float)):
            resting_hr = int(avg_hr)
        else:
            resting_hr = None
        out[day] = {
            "sleep_hours": float(duration_s) / 3600.0,
            "hrv_overnight": int(hrv) if isinstance(hrv, (int, float)) else None,
            "resting_hr": resting_hr,
        }
    return out


def _parse_daily_readiness(payload: Any) -> dict[str, dict]:
    """Extract per-day {readiness_score}."""
    out: dict[str, dict] = {}
    for row in _iter_rows(payload):
        day = row.get("day")
        if not isinstance(day, str) or not day:
            continue
        score = row.get("score")
        out[day] = {
            "readiness_score": int(score) if isinstance(score, (int, float)) else None,
        }
    return out


def _parse_daily_activity(payload: Any) -> dict[str, dict]:
    """Extract per-day {steps}."""
    out: dict[str, dict] = {}
    for row in _iter_rows(payload):
        day = row.get("day")
        if not isinstance(day, str) or not day:
            continue
        steps = row.get("steps")
        out[day] = {
            "steps": int(steps) if isinstance(steps, (int, float)) else None,
        }
    return out


def _merge_by_day(
    daily_sleep: dict[str, dict],
    sleep_sessions: dict[str, dict],
    readiness: dict[str, dict],
    activity: dict[str, dict],
) -> list[DailySummary]:
    """Union the day-keyed dicts, build DailySummary per day, drop fully-empty days.

    Four sources: `/daily_sleep` (score), `/sleep` (duration/HRV/HR),
    `/daily_readiness` (readiness score), `/daily_activity` (steps).

    Returns results sorted by day ascending.
    """
    all_days: set[str] = (
        set(daily_sleep) | set(sleep_sessions) | set(readiness) | set(activity)
    )
    out: list[DailySummary] = []
    for day in sorted(all_days):
        ds = daily_sleep.get(day, {})
        ss = sleep_sessions.get(day, {})
        r = readiness.get(day, {})
        a = activity.get(day, {})
        summary = DailySummary(
            day=day,
            sleep_hours=ss.get("sleep_hours"),
            sleep_score=ds.get("sleep_score"),
            readiness_score=r.get("readiness_score"),
            hrv_overnight=ss.get("hrv_overnight"),
            steps=a.get("steps"),
            resting_hr=ss.get("resting_hr"),
        )
        if summary.is_empty():
            continue
        out.append(summary)
    return out


# ── HTTP client (network shell around the parsers) ───────────────────


@dataclass
class OuraClient:
    """Thin httpx wrapper. One client per account per run (matches jamie/gmeet pattern)."""

    api_key: str
    timeout_s: float = 30.0
    _logged_discovery: bool = field(default=False, init=False)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict:
        """GET /v2/usercollection/<endpoint>?<params>. Returns the bare JSON payload.

        Retries network failures + 5xx + 429 once with a short sleep. 401
        raises immediately (auth-fatal). Other non-200s raise as well.
        """
        url = f"{_BASE_URL}/{endpoint}"
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)

        for attempt in (1, 2):
            try:
                r = httpx.get(url, headers=self.headers, timeout=self.timeout_s)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise OuraAPIError(
                        f"network failure on {endpoint}: {type(e).__name__}: {e}"
                    ) from e
                log.warning("oura %s: %s — retrying once in 5s", endpoint, type(e).__name__)
                time.sleep(5)
                continue

            if r.status_code == 401:
                raise OuraAPIError(
                    f"401 on {endpoint} — PAT invalid or revoked. Regenerate at "
                    "cloud.ouraring.com/personal-access-tokens."
                )
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                if attempt == 2:
                    raise OuraAPIError(f"429 on {endpoint} after retry (waited {wait}s)")
                log.warning("oura %s: 429 rate-limit — sleeping %ds before retry", endpoint, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                if attempt == 2:
                    raise OuraAPIError(
                        f"persistent {r.status_code} on {endpoint}: {r.text[:200]}"
                    )
                log.warning("oura %s: %d — retrying once in 5s", endpoint, r.status_code)
                time.sleep(5)
                continue
            if r.status_code != 200:
                raise OuraAPIError(
                    f"unexpected {r.status_code} on {endpoint}: {r.text[:200]}"
                )

            try:
                envelope = r.json()
            except ValueError as e:
                raise OuraAPIError(f"non-JSON body on {endpoint}: {e}") from e
            if not isinstance(envelope, dict):
                raise OuraAPIError(
                    f"{endpoint} returned {type(envelope).__name__}, expected dict"
                )
            if not self._logged_discovery:
                log.debug("oura discovery: GET %s top-level keys=%s",
                          endpoint, sorted(envelope.keys()))
                self._logged_discovery = True
            return envelope

        raise OuraAPIError(f"unreachable: exhausted retries on {endpoint}")

    def _fetch_all_pages(self, endpoint: str, start_date: str, end_date: str) -> list[dict]:
        """Paginate the same endpoint until `next_token` is empty. Returns merged rows."""
        all_rows: list[dict] = []
        next_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "start_date": start_date,
                "end_date": end_date,
            }
            if next_token:
                params["next_token"] = next_token
            payload = self._get(endpoint, params)
            all_rows.extend(_iter_rows(payload))
            next_token = payload.get("next_token") if isinstance(payload, dict) else None
            if not next_token:
                return all_rows

    def fetch_daily_summaries(self, start_date: str, end_date: str) -> list[DailySummary]:
        """Pull all four endpoints for [start_date, end_date], merge by day.

        Four GETs per call (daily_sleep + sleep + daily_readiness + daily_activity).
        `/sleep` carries the heavy session-level metrics; the three `daily_*`
        endpoints carry the daily-rollup scores.
        """
        daily_sleep_rows = self._fetch_all_pages("daily_sleep", start_date, end_date)
        sleep_session_rows = self._fetch_all_pages("sleep", start_date, end_date)
        readiness_rows = self._fetch_all_pages("daily_readiness", start_date, end_date)
        activity_rows = self._fetch_all_pages("daily_activity", start_date, end_date)

        daily_sleep = _parse_daily_sleep({"data": daily_sleep_rows})
        sleep_sessions = _parse_sleep_sessions({"data": sleep_session_rows})
        readiness = _parse_daily_readiness({"data": readiness_rows})
        activity = _parse_daily_activity({"data": activity_rows})
        return _merge_by_day(daily_sleep, sleep_sessions, readiness, activity)
