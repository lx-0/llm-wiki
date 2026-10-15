"""Google Drive v3 thin client — the transport behind `collectors/gmeet.py`.

One ``GoogleDriveClient`` wraps an ``AuthorizedSession`` from
``core/google_oauth.py``: retry once on network / 429 / 5xx, raise
``DriveAPIError`` on 401 / 403 / persistent failure (``adapters/calendar/google.py``
follows the same shape). The OAuth scope is the consumer's choice — gmeet asks for
``drive.meet.readonly``. Log and error texts name gmeet and ``wiki gmeet-auth``, the
client's one consumer.

Endpoints used:

- ``GET /files`` — a folder by exact name; the Google Docs in a folder (paginated).
- ``GET /files/{id}`` — one file's metadata.
- ``GET /files/{id}/export`` — a Google Doc as markdown, text/plain as the fallback.

Reference: https://developers.google.com/drive/api/reference/rest/v3
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_DRIVE_BASE = "https://www.googleapis.com/drive/v3"
_DRIVE_DOC_MIME = "application/vnd.google-apps.document"
_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
# Markdown export is officially supported for Google Docs; text/plain is the
# fallback for the rare Doc that rejects markdown export.
_EXPORT_MIME = "text/markdown"
_EXPORT_FALLBACK_MIME = "text/plain"


class DriveAPIError(RuntimeError):
    """Raised on non-recoverable Drive API failures (401, persistent 5xx, schema)."""


@dataclass
class GoogleDriveClient:
    """Thin Drive v3 wrapper over a google-auth AuthorizedSession.

    Retry shape mirrors `collectors/jamie.py._JamieClient._get`: retry once on
    network error / 429 / 5xx, raise on 401 / persistent failure.
    """

    session: Any  # google.auth.transport.requests.AuthorizedSession
    timeout_s: float

    def _get(self, url: str, *, params: dict | None = None, expect_json: bool = True) -> Any:
        for attempt in (1, 2):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout_s)
            except Exception as e:
                if attempt == 2:
                    raise DriveAPIError(
                        f"network failure on GET {url}: {type(e).__name__}: {e}"
                    ) from e
                log.warning("gmeet GET %s: %s — retrying once in 5s", url, type(e).__name__)
                time.sleep(5)
                continue

            if r.status_code == 401:
                raise DriveAPIError(
                    "401 from Drive — token invalid or scope not granted. Re-run `wiki gmeet-auth`."
                )
            if r.status_code == 403:
                # 403 is non-recoverable here (scope/permission/export-size) —
                # surface the Drive message rather than retrying blindly.
                raise DriveAPIError(f"403 on GET {url}: {r.text[:200]}")
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                if attempt == 2:
                    raise DriveAPIError(f"429 on GET {url} after retry (waited {wait}s)")
                log.warning("gmeet GET %s: 429 — sleeping %ds before retry", url, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                if attempt == 2:
                    raise DriveAPIError(f"persistent {r.status_code} on GET {url}: {r.text[:200]}")
                log.warning("gmeet GET %s: %d — retrying once in 5s", url, r.status_code)
                time.sleep(5)
                continue
            if r.status_code != 200:
                raise DriveAPIError(f"unexpected {r.status_code} on GET {url}: {r.text[:200]}")

            if expect_json:
                return r.json()
            # Drive's files.export returns charset-less `text/markdown`, which
            # requests decodes as Latin-1 by default → `Ã¤` for `ä`. The bytes
            # are always UTF-8; pin the encoding before reading `.text`.
            r.encoding = "utf-8"
            return r.text

        raise DriveAPIError(f"unreachable: exhausted retries on GET {url}")

    def resolve_folder_id(self, name: str) -> str | None:
        """Find a folder by exact name. Returns None if not found or the narrow
        scope blocks the name search (caller falls back to a clear error)."""
        q = (
            f"name = '{name.replace(chr(39), chr(92) + chr(39))}' "
            f"and mimeType = '{_DRIVE_FOLDER_MIME}' and trashed = false"
        )
        try:
            payload = self._get(
                f"{_DRIVE_BASE}/files",
                params={"q": q, "fields": "files(id,name)", "pageSize": 10},
            )
        except DriveAPIError as e:
            log.warning("gmeet: folder name-search failed (%s) — set drive_folder_id explicitly", e)
            return None
        files = payload.get("files") or []
        if not files:
            return None
        return files[0].get("id")

    def list_docs(
        self,
        folder_id: str,
        *,
        since: str | None = None,
        limit: int | None = None,
    ) -> Iterator[dict]:
        """Yield Google-Doc file stubs in `folder_id`, oldest first.

        Stub fields: id, name, createdTime, modifiedTime, webViewLink.
        Paginates while `nextPageToken` is non-empty; stops after `limit`.
        """
        q_parts = [
            f"'{folder_id}' in parents",
            f"mimeType = '{_DRIVE_DOC_MIME}'",
            "trashed = false",
        ]
        if since:
            q_parts.append(f"createdTime > '{since}'")
        q = " and ".join(q_parts)

        seen = 0
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": q,
                "fields": "nextPageToken,files(id,name,createdTime,modifiedTime,webViewLink)",
                "orderBy": "createdTime",
                "pageSize": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get(f"{_DRIVE_BASE}/files", params=params)
            if not isinstance(payload, dict):
                raise DriveAPIError(f"files.list returned {type(payload).__name__}, expected dict")
            for item in payload.get("files") or []:
                yield item
                seen += 1
                if limit and seen >= limit:
                    return
            page_token = payload.get("nextPageToken")
            if not page_token:
                return

    def get_file(self, file_id: str, *, fields: str) -> Any:
        """One file's metadata (`files.get`); `fields` names the stub fields wanted."""
        return self._get(f"{_DRIVE_BASE}/files/{file_id}", params={"fields": fields})

    def export_doc(self, file_id: str) -> str:
        """Export a Google Doc as markdown text. Falls back to text/plain."""
        url = f"{_DRIVE_BASE}/files/{file_id}/export"
        try:
            return self._get(url, params={"mimeType": _EXPORT_MIME}, expect_json=False)
        except DriveAPIError as e:
            log.warning("gmeet: markdown export failed for %s (%s) — trying text/plain", file_id, e)
            return self._get(url, params={"mimeType": _EXPORT_FALLBACK_MIME}, expect_json=False)
