"""The Thunderbird reader must surface the text/html alternative.

Gemini meeting-notes mails are multipart/alternative and put the Drive doc-url
ONLY in the HTML part; the plaintext alternative drops it. `_extract_body` now
returns `(text, html)` so email-discovery can regex the link out of `body_html`.
"""

from __future__ import annotations

import email

from adapters.mailbox import thunderbird
from collectors import gmeet

_MULTIPART = """\
From: Gemini <gemini-notes@google.com>
Subject: Notizen
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b1"

--b1
Content-Type: text/plain; charset="utf-8"

Besprechungsnotizen öffnen
--b1
Content-Type: text/html; charset="utf-8"

<a href="https://docs.google.com/document/d/DOC123_abc/edit?usp=meet_tnfm_email">open</a>
--b1--
"""

_PLAIN_ONLY = """\
From: a@b.de
Subject: plain
Content-Type: text/plain; charset="utf-8"

just text, no html
"""


def test_multipart_alternative_populates_both() -> None:
    msg = email.message_from_string(_MULTIPART)
    text, html = thunderbird._extract_body(msg)
    assert "Besprechungsnotizen" in text
    assert html is not None and "docs.google.com/document/d/DOC123_abc" in html


def test_plain_only_html_is_none() -> None:
    msg = email.message_from_string(_PLAIN_ONLY)
    text, html = thunderbird._extract_body(msg)
    assert "just text" in text
    assert html is None


def test_extract_doc_id_from_html_body_end_to_end() -> None:
    """The two S01 pieces compose: reader gives html, extractor gives the id."""
    msg = email.message_from_string(_MULTIPART)
    _text, html = thunderbird._extract_body(msg)
    assert gmeet.extract_drive_doc_ids(html or "") == ["DOC123_abc"]
