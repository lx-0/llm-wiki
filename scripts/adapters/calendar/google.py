"""Google Calendar v3 thin client.

One ``GoogleCalendarClient`` wraps an ``AuthorizedSession`` from
``core/google_oauth.py``. The retry shape mirrors ``collectors/gmeet.py._DriveClient._get``:
retry once on network / 429 / 5xx, raise on 401 / persistent failure.

Scopes the operator-facing OAuth bootstrap requests: ``calendar.readonly``
(read-only access to all of the user's calendars + events). Same GCP
installed-app client works as Gmail / Drive — tokens are cached per
account, per scope set, by ``core/google_oauth.py``.

Endpoints used:

- ``GET /users/me/calendarList`` — list calendars visible to the user.
- ``GET /calendars/{id}/events`` — list events in a calendar window. Uses
  ``singleEvents=true`` so recurring series are expanded; the response
  carries ``recurringEventId`` on each instance, which the collector uses
  for the recurring-event-collapse pass.

Reference: https://developers.google.com/calendar/api/v3/reference
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator

log = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com/calendar/v3"

# Read-only across primary + secondary calendars. The narrower
# ``calendar.events.readonly`` scope would also work but ``calendar.readonly``
# is the documented read-side scope and matches the operator's existing
# Gmail / Drive consent pattern.
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class CalendarAPIError(RuntimeError):
    """Raised on non-recoverable Calendar API failures (401, persistent 5xx, schema)."""


@dataclass
class GoogleCalendarClient:
    """Thin REST wrapper over an authorised google-auth session.

    Retry behaviour matches the gmeet Drive client: retry once with backoff
    on network / 429 / 5xx; raise on 401, 403, persistent failure, or schema
    mismatch (the JSON envelope must be a dict).
    """

    session: Any  # google.auth.transport.requests.AuthorizedSession
    timeout_s: float = 30.0

    # ── HTTP layer ────────────────────────────────────────────────────

    def _get(self, url: str, *, params: dict | None = None) -> dict:
        for attempt in (1, 2):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout_s)
            except Exception as e:  # noqa: BLE001 — requests / urllib3 network layer
                if attempt == 2:
                    raise CalendarAPIError(
                        f"network failure on GET {url}: {type(e).__name__}: {e}"
                    ) from e
                log.warning("calendar GET %s: %s — retrying once in 5s",
                            url, type(e).__name__)
                time.sleep(5)
                continue

            if r.status_code == 401:
                raise CalendarAPIError(
                    "401 from Calendar — token invalid or scope not granted. "
                    "Re-run `wiki calendar-auth`."
                )
            if r.status_code == 403:
                raise CalendarAPIError(
                    f"403 on GET {url}: {r.text[:200]}"
                )
            if r.status_code == 404:
                raise CalendarAPIError(
                    f"404 on GET {url}: calendar id not found or not accessible"
                )
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                if attempt == 2:
                    raise CalendarAPIError(
                        f"429 on GET {url} after retry (waited {wait}s)"
                    )
                log.warning("calendar GET %s: 429 — sleeping %ds before retry",
                            url, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                if attempt == 2:
                    raise CalendarAPIError(
                        f"persistent {r.status_code} on GET {url}: {r.text[:200]}"
                    )
                log.warning("calendar GET %s: %d — retrying once in 5s",
                            url, r.status_code)
                time.sleep(5)
                continue
            if r.status_code != 200:
                raise CalendarAPIError(
                    f"unexpected {r.status_code} on GET {url}: {r.text[:200]}"
                )

            try:
                payload = r.json()
            except ValueError as e:
                raise CalendarAPIError(
                    f"non-JSON response from {url}: {type(e).__name__}: {e}"
                ) from e
            if not isinstance(payload, dict):
                raise CalendarAPIError(
                    f"{url} returned {type(payload).__name__}, expected dict"
                )
            return payload

        raise CalendarAPIError(f"unreachable: exhausted retries on GET {url}")

    # ── Resources ─────────────────────────────────────────────────────

    def list_calendars(self) -> list[dict]:
        """Enumerate calendars in the user's CalendarList. Returns the raw
        items so the caller can read ``id``, ``summary``, ``selected``,
        ``primary``, ``accessRole``, ``timeZone``, ``backgroundColor``."""
        out: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"maxResults": 250}
            if page_token:
                params["pageToken"] = page_token
            payload = self._get(f"{_API_BASE}/users/me/calendarList", params=params)
            items = payload.get("items") or []
            if not isinstance(items, list):
                raise CalendarAPIError(
                    f"calendarList.items is {type(items).__name__}, expected list"
                )
            out.extend(x for x in items if isinstance(x, dict))
            page_token = payload.get("nextPageToken")
            if not page_token:
                return out

    def list_events(
        self,
        calendar_id: str,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        updated_min: str | None = None,
        page_size: int = 250,
        limit: int | None = None,
    ) -> Iterator[dict]:
        """Yield event stubs from one calendar.

        Recurring series are expanded to instances (``singleEvents=true``);
        each instance carries the parent's ``recurringEventId`` so the
        collector can collapse the series to a single canonical concept
        page and reference it from each per-date rollup.

        Ordering: ``orderBy=startTime`` REQUIRES ``singleEvents=true`` — both
        flags must move together or the API rejects the call. Cancelled
        events are filtered out server-side via ``showDeleted=false``
        (the default, named explicitly here for clarity).

        ``updated_min`` is the watermark for delta sync — only events with
        ``updated >= updated_min`` are returned. Combine with ``time_min``
        for the future-mutation window.
        """
        params: dict[str, Any] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "showDeleted": "false",
            "maxResults": page_size,
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if updated_min:
            params["updatedMin"] = updated_min

        seen = 0
        page_token: str | None = None
        # Encode the calendar id — primary contains no special chars, but
        # user calendars are emails with `@` and `.`, which must be
        # urlencoded for the path segment. The session normally does this,
        # but Google Calendar's path-parameter encoding is conservative.
        from urllib.parse import quote
        cal_segment = quote(calendar_id, safe="")
        url = f"{_API_BASE}/calendars/{cal_segment}/events"

        while True:
            if page_token:
                params["pageToken"] = page_token
            payload = self._get(url, params=params)
            for item in payload.get("items") or []:
                if not isinstance(item, dict):
                    continue
                yield item
                seen += 1
                if limit and seen >= limit:
                    return
            page_token = payload.get("nextPageToken")
            if not page_token:
                return

    def get_event(self, calendar_id: str, event_id: str) -> dict:
        """Fetch a single event (used by the etag re-fetch path when a
        listed instance reports a changed etag)."""
        from urllib.parse import quote
        cal_segment = quote(calendar_id, safe="")
        evt_segment = quote(event_id, safe="")
        return self._get(f"{_API_BASE}/calendars/{cal_segment}/events/{evt_segment}")
