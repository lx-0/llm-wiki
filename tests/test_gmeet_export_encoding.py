"""Regression for the gmeet `export_doc` UTF-8 bug.

Drive's `files.export` returns charset-less `text/markdown`; `requests` then
decodes `.text` as Latin-1 by default → `Ã¤` for `ä`. `_DriveClient._get`
pins `r.encoding = "utf-8"` for the non-JSON branch. This test drives a fake
response whose `.text` honours `.encoding` (like `requests.Response`) and
asserts umlauts + emoji survive.
"""

from __future__ import annotations

from collectors import gmeet


class _FakeResp:
    def __init__(self, body: str) -> None:
        self.status_code = 200
        self.content = body.encode("utf-8")
        self.encoding: str | None = None  # requests' charset-less default
        self.headers: dict[str, str] = {}

    @property
    def text(self) -> str:
        # Mirrors requests.Response.text: decode .content with .encoding,
        # defaulting to Latin-1 when the server sent no charset.
        return self.content.decode(self.encoding or "latin-1", errors="replace")


class _FakeSession:
    def __init__(self, body: str) -> None:
        self._body = body

    def get(self, url, params=None, timeout=None):  # noqa: ANN001
        return _FakeResp(self._body)


def test_export_doc_decodes_utf8_not_latin1() -> None:
    body = "# Notizen\n\nGrüße aus München 🚀 — verlässt, Anhänge, Zukünftige"
    client = gmeet._DriveClient(session=_FakeSession(body), timeout_s=5.0)
    out = client.export_doc("any-id")
    assert out == body
    assert "ä" in out and "🚀" in out
    assert "Ã" not in out  # no mojibake
