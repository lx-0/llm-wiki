"""The Google Drive v3 client (`adapters/drive/google.py`) — the transport behind the
gmeet collector. Request shapes over a recording fake session; no network.

The client's retry ladder and the UTF-8 export pin are covered by
`tests/test_gmeet_export_encoding.py`; the collector's use of it by the gmeet tests.
"""

from __future__ import annotations

import pytest

from adapters.drive.google import DriveAPIError, GoogleDriveClient


class _Resp:
    def __init__(self, status: int, body: object = None) -> None:
        self.status_code = status
        self._body = body
        self.headers: dict[str, str] = {}
        self.text = "" if body is None else str(body)

    def json(self) -> object:
        return self._body


class _Session:
    def __init__(self, *responses: _Resp) -> None:
        self.responses = list(responses)
        self.requests: list[tuple] = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, params, timeout))
        return self.responses.pop(0)


def test_get_file_is_one_files_get_carrying_the_fields() -> None:
    meta = {"id": "DOC1", "name": "Sync – Transcript"}
    session = _Session(_Resp(200, meta))
    client = GoogleDriveClient(session=session, timeout_s=9.0)
    assert client.get_file("DOC1", fields="id,name") == meta
    assert session.requests == [
        ("https://www.googleapis.com/drive/v3/files/DOC1", {"fields": "id,name"}, 9.0)
    ]


def test_get_file_raises_the_typed_error() -> None:
    client = GoogleDriveClient(session=_Session(_Resp(404, "gone")), timeout_s=5.0)
    with pytest.raises(DriveAPIError, match="unexpected 404"):
        client.get_file("DOC2", fields="id")
